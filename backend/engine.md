# Eco Value Simulator — Engine Specification (`evs.engine`)

## 1. Architectural Principles

1. **Zero External I/O:** The engine is a pure, deterministic Python package. It contains no database queries, network requests, file reading, or system clock calls. All inputs (prices, recipes, parameters) are passed in already resolved.
2. **Deterministic Parity:** Floating-point numbers are handled with standard double precision (IEEE 754) to ensure bit-level parity with the cached values of `Pricing model.xlsx`.
3. **Auditable Corrections ($X1$–$X3$):** Legacy spreadsheet errors are corrected by default, but the engine supports dual-mode execution (`mode="corrected"` vs `mode="workbook"`) to verify legacy workbook parity during audits and cross-checks.
4. **Agent-Engine Decoupling:** The engine calculates validated mathematical formulas; the agent orchestrates tool calls, explains results, and surfaces flags. The LLM never computes numbers itself.
5. **Clear Layer Separation:** 
   - **Engine Layer (`evs.engine` / `app.engine`):** Pure calculation of costs, 4 pricing methods, margins, break-evens, and math-driven flags.
   - **Resolver / Service Layer (`evs.market` / `evs.services` / `period.py`):** Period blending, series selection, netback calculations (destination price minus freight), and data-freshness flags.
   - **Adapter Layer (`run.py`):** Thin facade that translates API store models and calls modular engine functions with backward compatibility.

---

## 2. Directory Structure

The engine is implemented as a modular package in `backend/app/engine/` (ready for packaging as `evs.engine`):

```text
backend/app/engine/
├── __init__.py                  # Public exports (evaluate, run_sulphur_sensitivity, types)
├── types.py                     # Pydantic v2 schemas: inputs, outputs, flags, notes, traces
├── cost.py                      # Raw material costing, D&A, and marketing unit costs
├── methods.py                   # 4 pricing methods: Cost-Plus, Ref-Minus, Value, Market
├── margin.py                    # CGM per ton product, per ton P2O5, per ton S, waterfall
├── sensitivity.py               # Sulphur price parameter sweep & analytical break-evens
├── flags.py                     # Rule-based flag & audit note generators
├── core.py                      # Orchestration entry point (evaluate, evaluate_product)
├── period.py                    # Analysis periods & day-weighted snapshot blending (resolver)
└── run.py                       # Store & API adapter (delegates math to modular engine)

backend/tests/engine/
├── test_golden.py               # 25 acceptance values from Doc 09 §8 / Doc 10 §B8
├── test_corrections.py          # Validation of X1, X2, and workbook vs corrected modes
└── test_sensitivity.py          # Sulphur sweep, zero-margin, and crossover break-even validation
```

---

## 3. Data Contracts (`types.py`)

### 3.1 Input Models

* **`IngredientRecipe`**: Consumption coefficients per ton of product ($t\text{ ingredient} / t\text{ product}$) for Ammonia, KCl, Dry Rock, Wet Rock, and Sulphur. Intermediate ACP is unpriced.
* **`ProductDef`**: Product metadata, composition nutrient fractions ($N, P_2O_5, K_2O, S \in [0, 1]$), product carbon footprint ($\text{PCF}$ in $t\text{ CO}_2 / t\text{ product}$), placeholder status, and optional per-product D&A overrides.
* **`InputPrices`**: Prices for raw ingredients ($USD/t$): Ammonia, KCl, Dry Rock, Wet Rock, Sulphur.
* **`AgronomyData`**: Agronomic trial impact per product-reference pair: yield impact ($t\text{ crop}/ha$ vs reference), new product application rate ($t/ha$), reference application rate ($t/ha$), target crop price ($USD/t$), and status (`real` vs `placeholder`).
* **`EngineParams`**: 
  - `cost_plus_margin`: Default $0.20$ ($20\%$).
  - `marketing_pct`: Default $0.00$ ($0\%$).
  - `include_dna`: Boolean toggle (default `False`).
  - `dna_per_ton`: Default $96.00\text{ USD/t}$.
  - `value_share`: Default $1/3$ ($33.33\%$).
  - `anchor_method`: `refMinus`, `costPlus`, `value`, or `market` (default `refMinus`).
  - `carbon_price`: Default $0.00\text{ USD/t CO}_2$.
  - `nutrient_factors`: Ratios for pure nutrient conversion ($N/\text{NH}_3 = 0.82$, $K_2O/\text{KCl} = 0.60$).
  - `include_ref_marketing`: Boolean toggle (default `False`, matching workbook behavior where the reference bears no marketing).
* **`EngineInput`**:
  - `products`: Dictionary of `ProductDef` keyed by product ID.
  - `product_ids`: List of new product IDs to evaluate.
  - `reference_id`: Reference product ID (e.g., `'TSP'`, `'DAP'`, `'MAP'`).
  - `methods`: List of active pricing methods (`['costPlus', 'refMinus', 'value', 'market']`).
  - `cost_prices`: `InputPrices` used for raw material costing (from budget path or market period).
  - `nutrient_prices`: Optional `InputPrices` used for nutrient valuation in Reference-Minus (default equals `cost_prices`; allows reference market prices per Decision D-V1).
  - `reference_price`: Resolved price for reference product ($USD/t\text{ FOB}$ or netback).
  - `benchmark_price`: Optional competitor benchmark price ($USD/t$) for Market Pricing.
  - `agronomy`: Mapping of product ID to `AgronomyData` (or `None`).
  - `volume`: Optional volume ($t/\text{yr}$) for aggregate margin calculation.
  - `mode`: Execution mode (`"corrected"` [default] or `"workbook"`).

### 3.2 Output Models

* **`MethodResult`**: Method identifier, label, computed price, CGM, CGM per ton $P_2O_5$, total annual margin, and delta vs reference CGM.
* **`ProductResult`**: Unit costs breakdown, 4 pricing method outputs, price corridor (floor, anchor, ceiling), CGMs (per ton product, per ton $P_2O_5$, per ton $S$), reference metrics, waterfall steps, carbon scenarios, and volume margin.
* **`Flag`**: Code, severity (`error`, `warning`, `info`, `resolved`), title, detail explanation, and suggested action.
* **`Note`**: Legacy formula correction explanation, cell reference, old workbook value, engine value, and operational impact ($X1, X2$, nutrient price source).
* **`TraceEntry`**: Audit trail of intermediate values and formula steps.
* **`SensitivityPoint`**: Point in the sulphur price sweep ($P_S, \text{CGM}_{\text{new}}, \text{CGM}_{\text{ref}}, \Delta\text{CGM}$).
* **`BreakEven`**: Analytical break-even point with `product_id`, `sulphur_price`, `kind` (`'zero_margin'` or `'crossover'`), and descriptive note.
* **`SensitivityResult`**: Aggregated sweep results containing `points` and `break_evens`.
* **`EngineOutput`**: Aggregated result bundle returned by `evaluate()` containing `per_product`, `flags`, `notes`, and `trace`.

---

## 4. Mathematical Engine Specifications

### 4.1 Costing (`cost.py`)

* **Raw Material Unit Cost ($c(p)$):**
  $$c(p) = \sum_{i \in \text{Ingredients}} \text{recipe}[p][i] \times \text{cost\_prices}[i]$$
  *Priced ingredients:* Ammonia, KCl, Rock-Dry, Rock-Wet, Sulphur (intermediate ACP is unpriced).

* **Base Unit Cost:**
  $$\text{Base Cost} = c(p) + (\text{D\&A per ton if enabled else } 0)$$

* **Marketing Unit Cost:**
  $$\text{Marketing Cost} = \text{Base Cost} \times \text{marketing\_pct}$$

* **Total Unit Cost:**
  $$\text{Total Cost} = \text{Base Cost} + \text{Marketing Cost}$$

---

### 4.2 The Four Pricing Methods (`methods.py`)

#### 1. Cost-Plus ($E4$)
$$\text{Price}_{\text{cost\_plus}} = \text{Total Cost} \times (1 + \text{cost\_plus\_margin})$$

#### 2. Reference-Minus ($E13$–$E16$)
* **Nutrient unit valuations ($USD/t$ pure nutrient):**
  $$v_N = \frac{\text{nutrient\_prices}[\text{ammonia}]}{0.82}, \quad v_{K_2O} = \frac{\text{nutrient\_prices}[\text{kcl}]}{0.60}, \quad v_S = \text{nutrient\_prices}[\text{sulphur}]$$
  *(By default, nutrient prices follow the cost basis; per Decision D-V1, they can optionally follow the market prices of the reference period).*

* **Reference pure phosphate valuation:**
  $$\text{Pure P}_{\text{ref}} = \text{Price}_{\text{ref}} - \left(N_{\text{ref}} \cdot v_N + K_2O_{\text{ref}} \cdot v_{K_2O} + S_{\text{ref}} \cdot v_S\right)$$
  $$v_{P_2O_5} = \frac{\text{Pure P}_{\text{ref}}}{P_2O_{5, \text{ref}}}$$
  *Note:* $N, K_2O, S$ are the **chemical composition fractions** of the fertilizer ($[0, 1]$). For TSP, $N=0, K_2O=0, S=0$, so $\text{Pure P}_{\text{ref}} = \text{Price}_{\text{ref}}$.

* **New product reference-minus valuation:**
  $$\text{Price}_{\text{ref\_minus}} = P_2O_{5, \text{new}} \cdot v_{P_2O_5} + N_{\text{new}} \cdot v_N + K_2O_{\text{new}} \cdot v_{K_2O} + S_{\text{new}} \cdot v_S$$

#### 3. Value Pricing ($E7$–$E12$)
* **Agronomic value created per ton product:**
  $$\Delta\text{Crop} = \frac{\text{yield\_gain}}{\text{app\_rate}_{\text{new}}}$$
  $$\text{Value Created} = \Delta\text{Crop} \times \text{crop\_price}$$

* **Carbon emission differential:**
  $$\Delta\text{Carbon}_{\text{ha}} = \text{PCF}_{\text{ref}} \cdot \text{app\_rate}_{\text{ref}} - \text{PCF}_{\text{new}} \cdot \text{app\_rate}_{\text{new}}$$
  $$\Delta\text{Carbon}_{\text{ton}} = \frac{\Delta\text{Carbon}_{\text{ha}}}{\text{app\_rate}_{\text{new}}}$$

* **Carbon premium calculation (Correction $X1$):**
  $$\text{Carbon Effect} = \begin{cases} 
    \Delta\text{Carbon}_{\text{ton}} \times \text{carbon\_price} & \text{if } \text{mode} = \text{"corrected"} \\ 
    \Delta\text{Carbon}_{\text{ha}} \times \text{carbon\_price} & \text{if } \text{mode} = \text{"workbook"} 
  \end{cases}$$

* **Final value price:**
  $$\text{Price}_{\text{value}} = \text{Price}_{\text{ref}} + (\text{Value Created} \times \text{value\_share}) + \text{Carbon Effect}$$
  *(Emits flag $A3$ and marks value pricing as "needs input" if no agronomic data is available).*

#### 4. Market Pricing ($E17$)
$$\text{Price}_{\text{market}} = \text{benchmark\_price}$$
*(Emits flag $M1$ when no competitor benchmark is supplied).*

---

### 4.3 Margin & Profitability (`margin.py`)

* **Contribution Gross Margin (CGM) of New Product (Correction $X2$):**
  $$\text{CGM}_{\text{new}} = \begin{cases} 
    \text{Price}_{\text{anchor}} - \text{Total Cost} & \text{if } \text{mode} = \text{"corrected"} \\ 
    \text{Price}_{\text{anchor}} - \text{Total Cost} + \text{Marketing Cost} & \text{if } \text{mode} = \text{"workbook"} 
  \end{cases}$$

* **Reference Product CGM (Decision R2):**
  $$\text{CGM}_{\text{ref}} = \text{Price}_{\text{ref}} - \text{Base Cost}_{\text{ref}} - (\text{Marketing Cost}_{\text{ref}} \text{ if } \text{include\_ref\_marketing} \text{ else } 0)$$
  *(In the legacy workbook, the reference bears no marketing cost. When marketing $>0\%$, flag $M2$ explains this difference).*

* **Normalized Nutrient Margins:**
  $$\text{CGM}_{P_2O_5} = \frac{\text{CGM}_{\text{new}}}{P_2O_{5, \text{new}}}$$
  $$\text{CGM}_S = \frac{\text{CGM}_{\text{new}}}{\text{recipe}[\text{new}][\text{sulphur}]}$$

* **Total Annual Margin:**
  $$\text{Total Margin} = \text{CGM}_{\text{new}} \times \text{volume}$$
  *(Emits flag $V1$ if volume is omitted).*

* **Margin Waterfall Steps:**
  1. Reference CGM: $[0 \to \text{CGM}_{\text{ref}}]$ (kind: total)
  2. Price effect: $[\text{CGM}_{\text{ref}} \to \text{CGM}_{\text{ref}} + (\text{Price}_{\text{anchor}} - \text{Price}_{\text{ref}})]$ (kind: delta)
  3. Raw-material cost savings: $[(\dots) \to (\dots) + (\text{Cost}_{\text{ref}} - \text{Cost}_{\text{new}})]$ (kind: delta)
  4. New Product CGM: $[0 \to \text{CGM}_{\text{new}}]$ (kind: total)

---

### 4.4 Sensitivity Analysis (`sensitivity.py`)

The sensitivity module sweeps the sulphur price $P_S \in [100, 1000]\text{ USD/t}$ (default step: 50 USD/t) while holding all other inputs and reference price fixed.

Because costs and margins are linear functions of $P_S$, two distinct analytical break-evens are resolved:

1. **Zero-Margin Break-Even ($P_S^*$ where $\text{CGM} = 0$):**
   The sulphur price at which a product's margin drops to zero.
   $$\text{CGM}(P_S^*) = 0 \implies P_S^*(p) = \frac{\frac{\text{Price}}{1 + \text{marketing\_pct}} - \left(c_{\text{non-S}} + \text{D\&A}\right)}{\text{recipe}[p][\text{sulphur}]}$$
   - *Phosfusion 65-35 at parity:* **$918.86\text{ USD/t}$**
   - *TSP at parity:* **$870.41\text{ USD/t}$**

2. **Parity Crossover Break-Even ($P_S^{\text{cross}}$ where $\Delta\text{CGM} = 0$):**
   The sulphur price where Phosfusion 65-35 and TSP have identical margins ($\text{CGM}_{\text{new}} = \text{CGM}_{\text{ref}}$).
   $$P_S^{\text{cross}} = \frac{(\text{Price}_{\text{new}} - c_{\text{non-S, new}}) - (\text{Price}_{\text{ref}} - c_{\text{non-S, ref}})}{\text{recipe}[\text{new}][\text{sulphur}] - \text{recipe}[\text{ref}][\text{sulphur}]}$$
   - *At parity fixture:* **$848.46\text{ USD/t}$**

* **API Endpoint:** Exposed to the frontend via `POST /api/engine/sensitivity`, accepting `productId`, `referenceId`, `fromPrice`, `toPrice`, `step`, and returning `SensitivityResult`.

---

## 5. Audit & Formula Corrections ($X1$–$X3$)

| ID | Issue in `Pricing model.xlsx` | Corrected Formula in Engine | Runtime Behavior |
|---|---|---|---|
| **$X1$** | Cell `H48`: Multiplies carbon savings per **hectare** by carbon price ($H55 \times H57$). *(07 Oct version partially updated to $H56 \times H57$)*. | Converts savings to per **ton product**: $\Delta\text{Carbon}_{\text{ton}} \times \text{carbon\_price}$. | Generates `Note(code="X1")`. Parity test at 40 USD/tCO₂ yields **+2.47 USD/t** vs legacy **+0.40 USD/t**. |
| **$X2$** | Cell `H92`: Marketing is added back (`H32 - H23 + H27`), canceling marketing cost entirely. | $\text{CGM} = \text{Price} - \text{Total Cost}$ (marketing retained as an expense). | Generates `Note(code="X2")`. At 10% marketing, CGM drops to **-28.07 USD/t** vs legacy **+3.02 USD/t**. |
| **$X3$** | Cell `INDEX` lookups return 0 or blank on missing series quotes, causing silent fallbacks. | Forbids silent substitutions; raises flag $X3$ with available quote options (Low, High, Average). | Resolves deterministic error state with selectable option chips. |

---

## 6. Flag Catalog & Engine Rules (`flags.py`)

### 6.1 Pure Engine Flags (Math & Data Rules)
* **`P1` (Warning):** Anchor price is below the cost-plus floor ($\text{Price}_{\text{anchor}} < \text{Price}_{\text{cost\_plus}}$). Labelled "Anchor (below floor)".
* **`W1` (Warning / Open Item):** Yield impact label is ambiguously marked `%` in cell `E40` but used as $t/ha$ ($0.12$).
* **`W2` (Info / Recommendation):** Recommends the budget year (2026–2035) whose raw-material costs are closest to today's market prices (Decision G3). Under 2026 budget prices, explains elevated sulphur ($900\text{ USD/t}$ vs $285$ in 2027).
* **`M1` (Info):** Market pricing method active but competitor benchmark input is missing.
* **`M2` (Info):** Marketing percentage $>0\%$ applied to new product only (matching workbook behavior, Decision R2).
* **`C1` (Info):** Carbon price is set to 0; carbon effect excluded from value pricing.
* **`C2` (Warning):** Product carbon footprint marked as placeholder/dummy in product definition.
* **`A2` (Warning):** Agronomic trial data is synthetic/placeholder.
* **`A3` (Info):** No agronomic trial data available for the product-reference pair; value pricing requires input.
* **`V1` (Info):** Total volume not provided; aggregate annual margin calculation bypassed.
* **`X3` (Warning):** Selected price series lacks the requested quote type, or low > high quote detected.

### 6.2 Service / Resolver Flags (Layered Outside Engine Core)
*These flags are generated by the resolver/service layer before calling the engine:*
* **`D1` (Warning):** Price series and freight series end dates differ by more than the freshness threshold.
* **`D2` (Info):** Dataset data-through date is older than the stale threshold.
* **`D3` (Info):** Freight carried forward from an earlier week in the netback calculation.
* **`S2` (Warning):** Default or selected series not found in active uploaded files.
* **`N1` (Error):** No reference price available for the selected period/conditions.
* **`I1` (Info):** Market history raw-material series not yet selected by the user (Decision R1).
* **`U2` (Info):** Non-USD or non-metric series excluded from calculations.

---

## 7. Golden Values & Acceptance Testing (`test_golden.py`)

### 7.1 Test Baseline Fixture (Phosfusion 65-35 vs TSP)
- **Reference Price:** 640.00 USD/t (Parity Test Fixture, Argus 21 Apr)
- **Raw Material Costs (Budget 2026):** Ammonia 460, KCl 340, Dry Rock 120, Wet Rock 120, Sulphur 900 USD/t
- **Composition Phosfusion 65-35:** $N=0, P_2O_5=0.225625, K_2O=0, S=0$
- **Composition TSP:** $N=0, P_2O_5=0.46, K_2O=0, S=0$
- **Recipe Phosfusion 65-35:** Rock-Dry 0.738233, Rock-Wet 0.65309725, Sulphur 0.15993
- **Recipe TSP:** Rock-Dry 0.608, Rock-Wet 1.004765, Sulphur 0.512938
- **Agronomy:** Yield gain 0.12 t/ha, New rate 0.162 t/ha, Ref rate 0.13 t/ha, Crop price 409 USD/t
- **Parameters:** Cost-plus 20%, Value share 1/3, Marketing 0%, Carbon price 0 USD/t, D&A OFF

### 7.2 Acceptance Table (Tolerance: $\pm 0.01$)

| Target Metric | Expected Golden Value | Formula Reference & Correct Arithmetic |
|---|---|---|
| **Raw Material Cost (Phosfusion 65-35)** | **310.90 USD/t** | $0.738233(120) + 0.65309725(120) + 0.15993(900)$ |
| **Reference Cost (TSP)** | **655.18 USD/t** | $0.608(120) + 1.004765(120) + 0.512938(900)$ |
| **Cost-Plus Price** | **373.08 USD/t** | $310.8966 \times 1.20$ |
| **Pure $P_2O_5$ Value in TSP** | **1,391.30 USD/t** | $(640 - 0) / 0.46$ *(TSP nutrient composition has $0\%$ S)* |
| **Reference-Minus Price (Anchor)** | **313.91 USD/t** | $0.225625 \times 1391.3043$ *(Phosfusion nutrient composition has $0\%$ S)* |
| **Agronomic Value Created** | **302.96 USD/t** | $(0.12 / 0.162) \times 409$ |
| **Value Pricing** | **740.99 USD/t** | $640 + (302.96296 \times 1/3)$ |
| **CGM at Anchor** | **3.02 USD/t** | $313.91304 - 310.89663$ |
| **Reference CGM (TSP)** | **-15.18 USD/t** | $640 - 655.176$ |
| **CGM per ton $P_2O_5$** | **13.37 USD/t** | $3.01641 / 0.225625$ |
| **CGM per ton Sulphur** | **18.86 USD/t** | $3.01641 / 0.15993$ *(divided by recipe sulphur consumption)* |
| **Value Share at 50%** | **791.48 USD/t** | $640 + (302.96296 \times 0.50)$ |
| **Carbon at 40 USD/t ($X1$)** | **+2.47 USD/t ($743.46$)** | $\Delta\text{Carbon}_{\text{ton}} \times 40 = 0.061728 \times 40$ |
| **Marketing at 10% ($X2$)** | **-28.07 USD/t** | $\text{Unit Cost } 341.99, \text{ Cost-Plus } 410.38, 313.91 - 341.99$ |
| **Budget 2027 Conditions** | **Unit Cost 212.54 / CGM 101.37** | Sulphur at 285 USD/t |
| **Sulphur Break-Even (Zero-CGM)** | **Phosfusion: 918.86 / TSP: 870.41** | Zero-margin sulphur price where $\text{CGM}(P_S) = 0$ |
| **Sulphur Parity Crossover** | **848.46 USD/t** | Crossover sulphur price where $\text{CGM}_{\text{phos}} = \text{CGM}_{\text{tsp}}$ |

---

## 8. Test Suites & Verification

The calculation engine is verified by both unit and integration regression test suites:

1. **Modular Engine Test Suite (`backend/tests/engine/`):**
   - [`test_golden.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/tests/engine/test_golden.py): 25 acceptance values from Doc 09 §8 / Doc 10 §B8 tested within $\pm 0.01$ tolerance.
   - [`test_corrections.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/tests/engine/test_corrections.py): Verification of dual-mode execution (`mode="corrected"` vs `mode="workbook"`) for $X1$ and $X2$.
   - [`test_sensitivity.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/tests/engine/test_sensitivity.py): Parameter sweeps and analytical zero-margin and crossover break-evens.

2. **Integration & Backward Compatibility:**
   - [`test_engine.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/tests/test_engine.py): Full golden regression suite ported from TypeScript.
   - [`test_api.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/tests/test_api.py): FastAPI route integration including `POST /api/engine/run` and `POST /api/engine/sensitivity`.

**Execution Command:**
```bash
uv run --with-requirements requirements.txt pytest tests/engine/
```