# 01 · Product Spec

## 1. Problem

OCP is developing new phosphate fertilizers (e.g. **Phosfusion 65-35**). Deciding *at what price a new product can be sold profitably and competitively* today means a manual Excel business case: Argus/CRU prices, standard production cost, recipes, agronomic trials, crop prices and carbon data are scattered across files and re-keyed per product. Each pricing method uses different logic, inconsistencies between sources go unnoticed, and the result is hard to explain or audit.

## 2. Product

**Eco Value Simulator** — a chat-first workspace where a pricing manager asks a question ("Price Phosfusion 65-35 against TSP"), an AI agent gathers and checks the inputs, a validated engine runs four pricing methods, and the user gets a recommended price corridor, margin per ton and in total, comparison against the reference product and past years, a plain-language decision memo with sources, and an audit trail.

### Users (demo scope: one implicit user)

| Persona | Needs | Demo treatment |
|---|---|---|
| **Pricing manager / business developer** (primary) | Fast, defensible price for a new product; understand *why*; try what-ifs | The only logged-in persona |
| **Product & pricing team / Finance** (reviewer) | Validate rules; answer the agent's questions | Mocked: the user answers the agent's questions themselves |

## 3. Hero story (the demo)

1. Home: user clicks the suggestion **"Price Phosfusion 65-35 against TSP"** (or types it).
2. Agent streams steps: reads Prices, Standard cost, Agro trials, Crop prices → checks freshness → builds inputs.
3. Agent raises a **question chip** in the thread: *"TSP full production cost differs between sources: 494 USD/t (business-case deck) vs 655 USD/t (Standard cost 2026). Which should I use?"* → user picks **655 (Standard cost)** or **494**.
4. Engine runs four methods → result card in the Ask AI panel (mini ladder + 3 KPIs + flags). The page itself fills in.
5. The simulation page (opened automatically as soon as the run starts) shows **Costing · Pricing · Margin · Overview**. Overview: KPIs, price ladder, four graphs, flags still to resolve (anchor below floor, stale prices, yield unit, placeholder carbon footprint).
6. User asks Ask AI: *"What if the value share is 50%?"* → **staged change card** → **Apply & re-run (v2)** → version compare shows value price 740.99 → 791.48 (640 + 302.96 × 50%).
7. User sets **Analysis period** to 2025 → banner "Viewing under analysis period 2025" → Across-years strip updates.
8. Opens **Memo**, exports PDF.

## 4. Scope

### In (demo)
- Chat home, history, ⌘K search, simulations as conversations
- Run form dialog; agent-driven runs
- Simulation page: Costing, Pricing, Margin, Overview (+ Hypotheses drawer); pivot bar; reference switcher; analysis-period picker; version chip + compare
- Four pricing methods + CGM per t / per t P2O5 / per t S / total
- Products library (12 seeded products, add/edit with recipe), Uploads (5 seeded files, upload review flow), Parameters
- Flags & provenance; staged-change confirm cards; memo; export
- Light + dark; desktop-first, mobile second

### Later (explicitly out of the demo)
Auth & roles, real approval workflow with Finance, data warehouse, real Demand Engine (country × crop), price elasticity, Carbon Engine with scenario modelling beyond 3 illustrative prices, iso-CGM pricing views (workbook rows 108–120), shareable links/email, French UI, tablet-specific polish, real file ingestion beyond the seeded parsers.

## 5. Functional requirements

| ID | Requirement |
|----|-------------|
| F1 | Create a simulation from chat or the Run form; each run produces an immutable **Run vN**. |
| F2 | Engine computes cost-plus, market, value and reference-minus per product, plus CGM per t, per t P2O5, per t S and total margin (workbook-faithful). |
| F3 | Every input carries **provenance** (source, date, or "You edited" / "Agent assumption"). |
| F4 | The agent detects and displays **flags**: source conflicts, stale/discrepant data, anchor below floor, unit anomalies, placeholders, missing inputs. |
| F5 | The agent **never changes inputs without a confirm card** and never produces numbers itself. |
| F6 | Version chip lists runs, supports **Compare with vN** (input diff + price/CGM delta). |
| F7 | Pivot bar (Product/Strategy/Metric, one pinned) controls Pricing, Margin and Dashboard charts. |
| F8 | Analysis-period picker (date range) re-blends prices and costs for that range; derived view with banner. |
| F9 | Uploads: choose type, agent "What I found" review, File date + Data through, discrepancy banner (threshold in Parameters). |
| F10 | Products: add/edit recipe (add ingredients), composition, footprint, agronomy; cost derived live. |
| F11 | Memo per run with Source chips; export PDF / Markdown / xlsx. |
| F12 | Desktop (≥1280) three-pane layout; mobile (<768) full core loop. |

## 6. Success criteria for the demo

- Hero story runs end-to-end in under 3 minutes without leaving the app.
- Every number on screen can be traced (Source chip → input → workbook cell) in ≤ 2 clicks.
- The flags make the "agent checks inconsistencies" claim visible without explanation.
- Looks like a finished product: monochrome, dense, precise (Vercel) with ChatGPT-grade chat ergonomics.

## 7. Glossary

| Term | Meaning |
|---|---|
| **CGM** | Contribution gross margin: price − unit cost (+ marketing add-back as per workbook). USD per t product, per t P2O5, per t S. |
| **TSP / DAP / MAP** | Triple super phosphate / diammonium / monoammonium phosphate — reference treatments. |
| **Phosfusion** | OCP's new fused phosphate product family (50-50, 65-35, 45-55 avg; "Controlled R. Confirmed" variants). |
| **FOB** | Free on board — price basis for Morocco quotes. |
| **Reference minus** | Price the new product by the nutrient value it delivers, valuing P2O5 at the reference product's price minus N/K/S value. |
| **Value pricing** | Reference price + share of the agronomic value created (+ carbon effect). |
| **Analysis period** | The date range a run analyses. Prices and input costs are the day-weighted blend of the yearly data inside it. 2021–2025 come from CRU annual averages; the current year from the workbook. |
| **Anchor** | The method whose price is the recommended price (default reference-minus). |
