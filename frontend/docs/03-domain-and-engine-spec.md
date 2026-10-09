# 03 · Domain & Engine Spec

The engine is a pure TypeScript module (`src/engine`). **Every formula below is traced to a cell in `Pricing model.xlsx`** (sheet *B Case template V0 – Phosfusion*, column H unless noted). The agent never computes; it calls the engine.

## 1. Entities

```ts
Product      { id, name, family, recipe: Record<Ingredient, number>,   // t ingredient / t product
               composition: {N,P2O5,K2O,S: number},                     // fractions (0.225625 = 22.56 %)
               pcf: number | null,                                      // t CO2 / t product
               appRate: number | null,                                  // t product / ha
               yieldGain: number | null,                                // t crop / ha vs reference (see flag U1)
               role: 'reference' | 'new' | 'both' }
Ingredient   'ammonia' | 'kcl' | 'rockDry' | 'rockWet' | 'sulphur' | string  // user may add
Snapshot     { id: 'today'|'2025'|…|'2021', label, asOf, inputs:{ammonia,kcl,rockDry,rockWet,sulphur}, refPrices:{DAP,MAP,TSP}:{low,high?}, sources }  // yearly data points
Parameters   { costPlusMargin=.20, fullCost=false, valueShare=1/3, marketingPct=0, dnaPerTon=96,
               marketShare=.05, rampTargetYear=2030, carbonMarket:'voluntary'|'cbam', priceType:'low'|'high',
               freshnessMonths=2, staleDays=30 }
RunInput     { simId, version, newProducts[], reference, periodFrom, periodTo, methods[], params(overrides), benchmark?, cropPrice, comment, resolved:{[flagId]:choice} }
Run          { id, version, input, provenance:{[field]:Source}, output:RunOutput, flags[], createdAt, createdBy:'user'|'agent', changeSet? }
Simulation   { id, title, runs[], thread[], createdAt, pinnedAxis }
Upload       { id, name, type:'prices'|'freight'|'agro'|'crop', uploadedAt, fileDate, dataThrough, series, rows, warnings[] }
Flag         { id, severity, scope, title, detail, action, resolved? }
```

## 2. Formulas (per new product *n*, reference *r*, snapshot *s*)

Let `c(p) = Σ recipe[p][i] × price_s[i]` over ingredients priced in the snapshot (ammonia, kcl, rockDry, rockWet, sulphur; **ACP is an intermediate and is not priced** — verified: Phosfusion 65-35 → 310.8966 = 0.738233×120 + 0.65309725×120 + 0.15993×900).

| # | Quantity | Formula | Workbook |
|---|---|---|---|
| E1 | Unit cost | `c(n) + (fullCost ? dnaPerTon : 0)` | H25–H26 (`H25 + H18*H17`) |
| E2 | Marketing | `marketingPct × E1` | H27 |
| E3 | Total unit cost | `E1 + E2` | H23 |
| E4 | **Cost-plus** | `E3 × (1 + costPlusMargin)` | H34 |
| E5 | Reference price | `refPrices[r][priceType]` (fallback low) | H64 |
| E6 | Reference cost | `c(r) + (fullCost ? dnaPerTon : 0)` | H12 |
| E7 | Added crop per t product | `yieldGain / appRate(n)` | H42 |
| E8 | Added value per t product | `E7 × cropPrice` | H44 |
| E9 | Carbon saving per ha | `pcf(r)×appRate(r) − pcf(n)×appRate(n)` | H55 |
| E10 | Carbon saving per t product | `E9 / appRate(n)` | H56 |
| E11 | Carbon effect (USD/t) | `E10 × carbonPrice` (0 if no price → flag C1) | H48 |
| E12 | **Value pricing** | `E8 × valueShare + E11 + E5` | H38 |
| E13 | Nutrient unit values | `vN = ammonia/0.82` · `vK2O = kcl/0.60` · `vS = sulphur` (USD per t nutrient) | derived to match DAP column (561.0 USD/t N) |
| E14 | Pure P value (ref) | `E5 − N_r·vN − K_r·vK − S_r·vS` | H69 |
| E15 | P2O5 value | `E14 / P2O5_r` (USD per t P2O5) | H71 |
| E16 | **Reference minus** | `P2O5_n·E15 + N_n·vN + K_n·vK + S_n·vS` | H73–H81 |
| E17 | **Market pricing** | user benchmark (USD/t) or *needs input* | H36 (blank) |
| E18 | Method price | the four above for methods enabled | — |
| E19 | Anchor price | price of `anchorMethod` (default reference-minus) | deck slide 9 |
| E20 | **CGM / t product** | `price − E3 + E2` (workbook: `H32−H23+H27`; with marketing 0 → price − cost) | H92 |
| E21 | Reference CGM | `E5 − E6` | H93 |
| E22 | CGM / t P2O5 | `CGM / P2O5_n` | H98 |
| E23 | CGM / t S | `CGM / recipe[n].sulphur` (t S per t product) | H104 |
| E24 | Volume (t/yr) | `addressable × marketShare` (addressable = 14,630,675 t) | deck slide 3 |
| E25 | Total margin (USD/yr) | `CGM × volume` | — |
| E26 | Corridor | `[min(floor, anchor), max(ceiling, anchor)]`, floor=E4, ceiling=E12 | D7 |
| E27 | Price ladder status | anchor < floor ⇒ flag **P1** | — |

**Ramp-up (illustrative):** share(year) rises linearly from 0 in 2026 to `marketShare` at `rampTargetYear`, flat to 2035. Label "Illustrative, not a forecast".

**Carbon scenarios (illustrative):** Voluntary-low 15, Voluntary-high 40, CBAM/EU-ETS-ref 75 USD/tCO₂. Value-pricing delta = `E10 × scenario`.

**Margin waterfall (TSP → new product, per t):** `TSP CGM` → `Δ price vs reference (anchor − E5)` → `Δ raw-material cost (E6 − E3)` → `New product CGM`. (Check: −15.18 + (313.91−640) + (655.18−310.90) = 3.02 ✓.)

## 3. Seed data (extracted from the workbooks)

### 3.1 Products (12) — recipes (t/t) & composition
| Product | NH3 | KCl | Rock dry | Rock wet | S | N | P2O5 | K2O | S |
|---|---|---|---|---|---|---|---|---|---|
| DAP | .262068 | 0 | 0 | 1.847652 | .65215 | .18 | .46 | 0 | 0 |
| MAP | .073502 | 0 | 0 | 1.584554 | .613128 | .11 | .52 | 0 | 0 |
| NPK | .131755 | .291069 | 0 | .909452 | .211749 | .15 | .15 | .15 | 0 |
| NPS | .10125 | 0 | 0 | 2.176 | .414862 | .12 | .45 | .05 | 0 |
| PhosGold 3 30 9S | .024729 | 0 | .605266 | .686938 | .247016 | .03 | .30 | 0 | .09 |
| TSP | 0 | 0 | .608 | 1.004765 | .512938 | 0 | .46 | 0 | 0 |
| TSP blendable 5 42 | .070602 | 0 | .502314 | .982566 | .396659 | .05 | .42 | 0 | 0 |
| Phosfusion 50-50 | 0 | 0 | .98 | .5023825 | .102719 | 0 | .190754 | 0 | 0 |
| Phosfusion 65-35 | 0 | 0 | .738233 | .65309725 | .15993 | 0 | .225625 | 0 | 0 |
| Phosfusion 50-50 — Controlled R. Confirmed | 0 | 0 | .552 | .5023825 | .179 | 0 | .301735 | 0 | 0 |
| Phosfusion 65-35 — Controlled R. Confirmed | 0 | 0 | .704405 | .65309725 | .267099 | 0 | .249315 | 0 | 0 |
| Phosfusion avg 45-55 — Controlled R. Confirmed | 0 | 0 | .680225 | .427025125 | .19418 | 0 | .277017 | 0 | 0 |

Other fields: PCF — DAP/MAP/TSP 0.7 (calculated); Phosfusion 0.5 (**dummy**, flag C2); others `null`. App rate — Phosfusion 0.162 t/ha, TSP 0.13 t/ha. Yield gain — Phosfusion 0.12 (first estimates, flag U1).

### 3.2 Snapshots
| Snapshot | Ammonia | KCl | Rock (dry/wet) | Sulphur | TSP | DAP | MAP | Source |
|---|---|---|---|---|---|---|---|---|
| **Today** | 460 | 340 | 120 | 900 | 640 (low only) | 820 / 855 | 853 / 880 | Workbook `Standard Production cost` 2026 & `Prices` (Argus, 21 Apr) |
| 2025 | 356.9 | 304.8 | 120 | 299.2 | 529.3 | 713.4 | 698.9 | CRU annual averages (Morocco FOB; NH3 & S Middle East; potash Vancouver) |
| 2024 | 360.1 | 259.5 | 120 | 102.8 | 436.1 | 585.5 | 593.8 | CRU |
| 2023 | 432.6 | 380.8 | 120 | 100.0 | 449.4 | 588.7 | 574.2 | CRU |
| 2022 | 991.3 | 624.2 | 120 | 277.3 | 820.9 | 968.9 | 969.9 | CRU |
| 2021 | 566.9 | 277.0 | 120 | 187.8 | 549.2 | 650.8 | 674.6 | CRU |

Rock is an OCP internal transfer cost (120 USD/t, constant) — not a market price.

### 3.2b Analysis period (replaces "market conditions")

A run analyses a date range `[periodFrom, periodTo]` (ISO dates, clamped to 01 Jan 2021 → today). The market data used is the **day-weighted blend** of the yearly snapshots above:
`weight(year) = days of the range inside that year ÷ days in the range`; 2026 maps to the **Today** snapshot (workbook current inputs).
- A range entirely inside 2026 (default **Year to date**) uses the Today snapshot untouched, so all golden values below are unchanged.
- Any other range blends linearly: e.g. 01 Jul 2024 – 30 Jun 2025 = 50.4 % of 2024 + 49.6 % of 2025.
- Flags: **S1** (TSP cost conflict) and the deck override only apply when the range is entirely current; **D1** applies whenever the range touches the current year.
- Presets: Year to date · Last 12 months · 2025 … 2021 · 2021–2025 · custom. Implementation: `src/engine/period.ts`.

### 3.3 Other inputs
Crop price 409 USD/t (target crop, placeholder "wheat"); current yield 3.4253 t/ha; addressable market 14,630,675 t; weight/units USD, metric tons.

### 3.4 Uploads (seeded)
| File | Type | File date | Data through | Notes |
|---|---|---|---|---|
| `argus-fob-morocco.xlsx` | Prices | 21 Apr 2026 | 21 Apr 2026 | DAP, MAP, TSP FOB quotes (from `Prices` sheet) |
| `fertilizer-week-historical-prices-averages-24-09-2026.xlsx` | Prices | 24 Sep 2026 | 24 Sep 2026 | 338 series, 1987→2026 |
| `fertilizer-week-historical-freights-24-09-2026.xlsx` | Freight | 24 Sep 2026 | 24 Sep 2026 | 10 commodity tabs |
| `agro-trials-phosfusion.xlsx` | Agro tests | 12 Aug 2026 | 12 Aug 2026 | Yield gain 0.12 t/ha, rate 0.162 t/ha |
| `crop-prices.csv` | Crop prices | 30 Sep 2026 | 30 Sep 2026 | 409 USD/t |

Latest upload (chip): **02 Oct 2026** (the CRU files uploaded that day).
Discrepancy rule: |Data-through(prices) − Data-through(freight)| ≥ `freshnessMonths` ⇒ warning. Argus (21 Apr) vs freight (24 Sep) = **5 months** ⇒ fires (demo moment F3).

## 4. Golden values (Today, TSP reference, price type low, cost-plus 20 %, value share ⅓, full cost off)

| Output | Phosfusion 65-35 | Phosfusion 50-50 |
|---|---|---|
| Unit cost | **310.90** | 270.33 |
| Cost-plus | **373.08** | 324.40 |
| Reference-minus | **313.91** | 265.40 |
| Value pricing | **740.99** (added value 302.96/t) | 740.99 |
| Reference price / cost | 640 / 655.18 | same |
| CGM at anchor | **3.02** | −4.94 |
| Reference CGM | **−15.18** | −15.18 |
| CGM / t P2O5 | 13.37 | — |
| P2O5 value in TSP | 1391.30 USD/t P2O5 | — |

Cross-snapshot (65-35 vs TSP, anchor = ref-minus): 2025 → 259.62 (cost 214.81, TSP CGM 182.30); 2024 → 213.90; 2023 → 220.43; 2022 → 402.64; 2021 → 269.38.
Against DAP (Today): reference-minus 352.88, value 920.99.
Value share 50 % → value 791.48. TSP cost 494 (deck) → reference CGM 146.00.

## 5. Flag catalogue (engine + agent raise these)

| ID | Sev | Trigger | Suggested action |
|---|---|---|---|
| **S1** | warning | Two sources disagree on a cost (TSP full cost: deck 494 vs workbook 655.18) | *Answer* chips: Use 655.18 / Use 494 / Open sources |
| **P1** | warning | Anchor < cost-plus floor (313.91 < 373.08) | Show amber segment; offer switch anchor or raise margin |
| **D1** | warning | Prices (Argus 21 Apr) vs freight (24 Sep) ≥ threshold | Open Uploads |
| **D2** | info | Latest upload stale > `staleDays` | Open Uploads |
| **U1** | warning | `Yield impact` labelled "%" but used as t/ha (0.12) | Confirm unit |
| **C1** | info | Carbon price = 0 → carbon effect excluded | Add a carbon price |
| **C2** | warning | Product PCF 0.5 is a placeholder ("dummy") | Open product |
| **M1** | info | Market pricing needs a competitor benchmark | Add benchmark |
| **A1** | info | Agent assumption: market share 5 % | Edit |
| **Q1** | info | TSP FOB quote has low (710) > high (691) | Check Argus file |
| **N1** | info | No data for this method in snapshot | — |

## 6. Validation rules
- Composition fractions in [0,1], Σ(N+P2O5+K2O+S) ≤ 1 (soft warning).
- Recipe quantities ≥ 0; at least one priced ingredient.
- Reference must have a price in the snapshot (DAP, MAP, TSP only) else **N1**.
- Cost-plus margin in [0, 100 %]; value share in [0, 100 %].
