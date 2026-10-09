# Eco Value Simulator — Spec Pack

AgentX · Nutricrops · Eco Value challenge track. A conversational pricing & margin simulator for new fertilizer products.

> **Principle (from the architecture diagram):** the agent gathers, checks and explains. The engine calculates with validated formulas. People decide.

## Documents

| # | File | Answers |
|---|------|---------|
| 01 | [Product spec](01-product-spec.md) | Why, for whom, what is in/out of scope, the hero demo story, requirements |
| 02 | [Information architecture & flows](02-information-architecture-and-flows.md) | Sitemap, navigation, key user flows, states |
| 03 | [Domain & engine spec](03-domain-and-engine-spec.md) | Data model, formulas (traced to workbook cells), seed data, golden numbers, flags |
| 04 | [Agent spec](04-agent-spec.md) | Autonomy tiers, tools, message types, demo script, tone |
| 05 | [Design system](05-design-system.md) | Monochrome tokens, type, components (shadcn + prompt-kit), charts, motion, responsive |
| 06 | [Screen specs](06-screen-specs.md) | Every screen: layout, components, states, desktop + mobile |
| 07 | [Tech spec](07-tech-spec.md) | React + Vite architecture, folders, state, engine, testing |
| 08 | [Figma & build plan](08-figma-and-build-plan.md) | Frame inventory and build order |

## Decision log (locked in the grill session, 2026-10-02)

| # | Decision |
|---|----------|
| D1 | Chat is the home. A **Simulation** = one conversation + its runs. The Run form is a secondary entry point. **There is no separate chat window (2026-10-05):** running a simulation redirects straight to the simulation page, where the agent works in the docked "Ask AI" panel (skeleton page until the first run exists). |
| D2 | Target is a **working demo/prototype** (seeded data, no auth, no roles). Target-vision items live in "Later". |
| D3 | **Hero story:** price *Phosfusion 65-35* against *TSP* across the four methods, resolve a flag, then ask a what-if. |
| D4 | **Workbook is the source of truth** for formulas and data. The deck's numbers are narrative only. The TSP cost conflict (494 vs 655) is a deliberate demo moment. |
| D5 | Sidebar: New simulation · Search · History · Library (Products, Uploads) · Parameters · User. |
| D6 | Results page has a **pivot bar**: Product / Strategy / Metric, one pinned. Default: Product pinned. A reference switcher ("TSP ▾") re-bases deltas. |
| D7 | **Price ladder:** floor = cost-plus, anchor (recommended) = reference-minus, ceiling = value pricing, market = tick when a benchmark is entered. |
| D8 | Chat shows **inline result card → opens split view**. Agent questions are answer chips in the thread. |
| D9 | **Runs are immutable.** Edits create versions (v1, v2…). Every input has a provenance badge. Version history = audit trail. |
| D10 | Uploads: agent-led review ("What I found"). Show both **File date** and **Data through** (last row). Default discrepancy threshold 2 months, editable in Parameters. |
| D11 | Products: grouped table (Recipe · Composition · Carbon footprint · Agronomy), side-sheet editor, composition typed in, cost derived. |
| D12 | Visual: **strictly black/white/grey (shadcn zinc/neutral)**, Vercel + ChatGPT inspired, **no brand color**. Functional amber/red allowed for flags only. Charts greyscale. |
| D13 | UI built on **shadcn/ui + prompt-kit** components. |
| D14 | Run form is a **dialog** with Essentials + collapsed Advanced. Shows data-freshness line above Run. |
| D15 | Volume = addressable market × editable share (default 5%, agent assumption) + illustrative ramp-up. No demand model. |
| D16 | **English** UI and agent output; agent understands French input. |
| D17 | Memo = per-run, rendered in thread and in a Memo sheet; Export = PDF, Markdown, xlsx. No memo tab. |
| D18 | Agent: reads/explains/runs automatically; **proposes input changes via confirm cards**; never computes numbers itself. |
| D19 | **Desktop first, mobile second** (full core loop on mobile; tables → cards). |
| D20 | Comparison = header controls **Analysis period** (date range, replaces "market conditions") and **Compare to ▾**; "Across years" strip on Pricing. Derived view, not a new run. |
| D21 | Tabs (2026-10-05): **Costing · Pricing · Margin · Overview** (Costing opens first). **Overview** (was Dashboard) holds KPI cards, price ladder, flags and four graphs. **Hypotheses is no longer a tab:** it opens in a drawer from a quiet header link, from flags, and from ⌘K. |
| D22 | Home is chat-only (no global dashboard). |
| D23 | **Analysis period** replaces market conditions: a date range (presets: Year to date, Last 12 months, 2025…2021, 2021–2025, or custom) between 01 Jan 2021 and today. Prices/costs are the **day-weighted blend** of the yearly data inside the range; a range inside the current year uses the workbook's current inputs exactly. |
| D25 | **Mascot animation** (2026-10-05): on Home and in the sidebar the mascot idles, then every 14–26 s plays a ~7 s routine (waves, calculator, puts on glasses) and returns to the identical idle frame. Built from a video into a 110-frame transparent sprite sheet (`public/mascot-sprite.webp`, 256×256 cells, one shared canvas so there is no size jitter); honours `prefers-reduced-motion`. |
| D24 | **Logo** (2026-10-05, revised): the plush sprout mascot from Figma node 33:24 (replaces the gradient visor mark from node 25:14), background removed, used in the sidebar, agent avatar, Home and favicon (`public/mascot.png`, `public/favicon.png`). It is the only coloured element in the UI. |

## Source material

- `Current approach.pptx` — Phosfusion 65-35 vs TSP business-case narrative
- `Pricing model.xlsx` — formulas, recipes, compositions, input prices, Argus quotes (source of truth)
- `fertilizer-week-historical-*.xlsx` — CRU price & freight history (real 2021–2026 snapshots)
- `How it works` / `Architecture` diagrams, `wireframes-initial/*`, `inspiration/*`
- `agentx_ecovalue.xlsx` — hackathon submission sheet (contains an API key — never copied into this repo; supply via `.env`)

## Build status (2026-10-02)

| Deliverable | Status |
|---|---|
| Spec pack (this folder) | Complete |
| Figma desktop frames S01–S20 + Cover & Tokens (Light/Dark variables) | Complete — `figma.com/design/vwGKCMMQ4RkPcFL3WJzRz4` |
| Figma mobile frames M01–M08 | Specified (doc 06), not drawn — the app implements the mobile layout |
| React + Vite demo app (`../`) | Complete — hero flow, all 5 tabs, version/compare, memo + export, Products, Uploads, Parameters, ⌘K, light/dark, mobile |
| Tests | 13 passing: engine golden values (workbook-traced) + scripted-agent hero path |

Deviations from the spec, by design:
- Charts are custom SVG (not Recharts) to match the greyscale/direct-label language exactly.
- prompt-kit `thinking-bar` has a broken registry dependency; progress uses `Steps` + `TextShimmer` instead. `Source` is replaced by a local `SourceChip` (prompt-kit's needs URLs).
- Playwright smoke test replaced by a headless Vitest test of the scripted agent (same hero path).
- Upload "parsing" is simulated (type/date detected from the filename); numbers stay seeded from the workbook.

## Change log — 2026-10-05

- Logo applied: first the Figma node 25:14 mark, then replaced by the sprout mascot (node 33:24).
- Chat window removed: Home → simulation page directly; the agent works in the Ask AI panel.
- Tabs reordered to Costing · Pricing · Margin · Overview; Hypotheses moved to a drawer.
- "Market conditions" replaced by **Analysis period** (Run form + **Hypotheses drawer**; a day, month, year or range; editing it creates a new version). The Product/Strategy/Metric pivot bar now appears on the **Overview** tab only.
- (superseded) previously: Analysis period was in the simulation header. `RunInput.snapshotId` became `periodFrom` / `periodTo` (see doc 03 §3.2).
- **The Figma desktop frames (S01–S20) still show the previous design** (chat view S02/S03, Dashboard/Hypotheses tabs, Conditions control). The code and these docs are the current source of truth.
