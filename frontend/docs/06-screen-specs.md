# 06 · Screen Specs

Desktop frames are 1440×900 (light unless noted). Mobile frames 390×844. IDs are used by the Figma plan (doc 08) and by test ids in the app.

Numbers shown are the **golden values** from doc 03 (Phosfusion 65-35 vs TSP, Today, answer S1 = 655.18).

---

> **Revisions 2026-10-05 (override the screen text below where they differ):**
> - **No chat window.** S02/S03 are no longer full-page screens: the thread (steps, question, result card) lives in the **Ask AI panel**, and the simulation page (skeleton while the agent works) is shown behind it.
> - **Tabs** are now Costing · Pricing · Margin · **Overview** (S05 content = Overview). **Hypotheses (S06) is a right-hand drawer**, opened from the quiet "Hypotheses" link beside the version chip, from flags and from ⌘K.
> - **"Conditions" / "Market conditions" → "Analysis period"** (date range picker with presets and a custom range) in the Run form (S04) and the header (S05, S18).
> - **Logo:** the sprout mascot (Figma node 33:24) replaces the black "E" tile everywhere.

## S01 · Home (empty)
- **Sidebar** per doc 02. History shows 3 seeded simulations (Today: "Phosfusion 65-35 vs TSP" ●; Yesterday: "Phosfusion 50-50 vs DAP"; Previous 7 days: "Sulphur spike sensitivity").
- **Main:** centered column (max 720). Greeting H1 28 "What do you want to price?" ; subtitle muted "Ask in plain words. I'll gather the data, check it, and run the engine."
- **Composer** (`PromptInput`): placeholder "Price Phosfusion 65-35 against TSP…"; left actions: **Attach** (paperclip), **Configure run** (sliders icon + label); right: send (solid black circle ↑). Shortcut hint ⌘⏎.
- **Suggestions** (`PromptSuggestion`, 2×2): "Price Phosfusion 65-35 against TSP" · "Compare Phosfusion 50-50 and 65-35" · "Check my data for gaps" · "What changed since the last upload?"
- **Footer:** `FreshnessChip` centered: ● `Latest upload · 02 Oct 2026 · Data through 24 Sep` (amber dot: prices 5 months older than freight).

## S02 · Thread — agent working (question pending)
- User message right-aligned bubble (`bg-muted`), assistant left with a 24px black-on-white "EV" avatar.
- `Steps` (collapsible, with checks): ✔ Reading Argus quotes (21 Apr) · ✔ Reading CRU prices & freight (24 Sep) · ✔ Building recipe cost: Phosfusion 65-35, TSP · ◌ Checking sources (`TextShimmer`).
- `SystemMessage` warning D1: "Prices (Argus, 21 Apr) are 5 months older than freight (24 Sep)." action *Open Uploads*.
- **Question message** with S1: text + chips `Use 655.18 · Standard cost 2026` · `Use 494 · Business-case deck` · `Open sources`. Composer disabled with hint "Answer the question above to continue".

## S03 · Thread — result card
- `Tool` row: "Pricing engine · 4 methods · v1 · 1.2 s".
- **ResultCard:** title "Phosfusion 65-35 vs TSP · v1"; mini ladder (floor 373.08 | anchor 313.91 amber-hatched below floor | ceiling 740.99 | TSP 640 line); KPIs: *Recommended 313.91 USD/t* · *CGM 3.02 USD/t (▲ 18.20 vs TSP −15.18)* · *Total margin 2.2 M USD/yr*; flags: P1 warning, M1 info; buttons *Open simulation* (primary), *Memo*.
- Assistant summary (3 sentences, `Source` chips). Remaining flags as `SystemMessage` (U1, C2, A1).
- `FeedbackBar` under the summary.

## S04 · Run form (dialog 560 w)
- Title "Configure run". **Essentials:** Products (multiselect combobox, "All" toggle; default Phosfusion 65-35) · Reference product (select, TSP) · Cost-plus margin % (20) · Methods (4 checkboxes, default all) · Market conditions (select: Today …2021) · Comment (textarea, "Why are you running this?").
- **Advanced** (collapsible): Price type Low/High · Carbon market Voluntary/CBAM · Value share % (33.3) · Full cost Yes/No (No). Overridden fields show ● edited.
- Footer line: `Prices 21 Apr · Freight 24 Sep ⚠ 5 months apart` (amber). Buttons: Cancel · **Run** (solid black, ⌘⏎).

## S05 · Simulation — Dashboard (default tab)
- **Header:** breadcrumb `Simulations / Phosfusion 65-35 vs TSP`; title (editable); `v1 ▾` · `Conditions: Today ▾` · `Compare to: TSP ▾` · `Memo` · `Export ▾`; `Ask AI` toggle (⌘/).
- **Pivot bar:** `Product ● Phosfusion 65-35 (pinned)` · `Strategy: All 4` · `Metric: Price USD/t`.
- **Tabs:** Dashboard · Hypotheses · Pricing · Costing · Margin.
- **KPI row (4):** Recommended price 313.91 · CGM/t 3.02 (▲ vs TSP −15.18) · CGM/t P2O5 13.37 · Total margin 2.2 M USD/yr.
- **Price ladder (full width)** with legend line.
- **Charts 2×2:** C1 price by method · C2 volume ramp-up · C3 CGM waterfall · C4 carbon scenarios (empty state: "Add a carbon price"). Each card: title, `⋯` menu (View as table, Export PNG).
- **Flags rail (right of KPIs on ≥1440, below on smaller):** "Flags to resolve · 6" with FlagRows (P1, D1, U1, C2, M1, A1).
- **Ask AI panel:** thread continues; composer at bottom.

## S06 · Hypotheses
Grouped form sections (collapsible cards), every row = label · value input · unit · `ProvenanceBadge`:
1. **Products** — New product (select), Reference (select), Price type.
2. **Costing** — Unit cost (read-only, from recipe), Marketing % (0), Full cost (switch), D&A (96 USD/t).
3. **Pricing** — Cost-plus margin (20 %), Anchor method (select), Market benchmark (input, empty).
4. **Value pricing** — Yield gain (0.12 t/ha ⚠ U1), Application rate (0.162), Crop price (409), Value share (33.3 %).
5. **Carbon** — Product PCF (0.5 ⚠ C2 "dummy"), Reference PCF (0.7), Reference rate (0.13), Carbon market, Carbon price (0).
6. **Volume** — Addressable (14,630,675 t, read-only), Market share (5 % · Agent assumption), Ramp target year (2030).
Edits are **staged**; a sticky bar appears: "3 changes · **Re-run (v2)** · Discard". Comment field is required to re-run (default "Edited hypotheses").

## S07 · Pricing
- Price ladder (large) with corridor annotations.
- **Method cards (2×2):** Cost-plus 373.08 · Reference minus 313.91 (Anchor chip) · Value pricing 740.99 · Market pricing "Needs input — Add benchmark". Each shows formula in words, inputs with badges, and an "Across years" mini sparkline.
- **Across years strip:** columns 2021 … 2025, Today with anchor price (269.38, 402.64, 220.43, 213.90, 259.62, 313.91); current column outlined.
- Pivot behaviors: if Strategy is pinned → rows are products; Metric pinned → matrix product × strategy.

## S08 · Costing
- KPI row: Unit cost 310.90 · TSP cost 655.18 · Δ −344.28 (▼ raw-material savings).
- **Stacked horizontal bar** per product by ingredient (ammonia, KCl, rock dry/wet, sulphur, marketing, D&A) with TSP ghost bar.
- **Table:** Ingredient · t/t · Price (year) · USD/t, editable cells with badges.
- **Input-price trend** small chart 2026→2034 (sulphur highlighted; sulphur 900→285 dominating TSP cost).

## S09 · Margin
- KPI cards: CGM/t · CGM/t P2O5 · CGM/t S (18.86) · Total margin.
- Table (sortable): Product × Method · Price · Cost · CGM/t · CGM/t P2O5 · Total margin · Δ vs TSP. Anchor row highlighted; formula line "CGM = price − unit cost (+ marketing)" with tooltip.

## S10 · Versions & compare (popover + state)
- `v2 ▾` popover: v2 (Agent · "value share 33 % → 50 %") · v1 (You · "Initial run"); *Compare with v1*.
- Compare mode: top strip "Comparing v2 with v1"; changed inputs show `33.3 % → 50 %`; deltas on KPIs ("Value pricing +50.49").

## S11 · Memo (sheet 560 w)
Header "Decision memo · v1" + *Copy*, *Export ▾*. Sections: Recommendation · Why · Margin vs TSP · Risks & open flags · Sources (`Source` chips list). `FeedbackBar` footer.

## S12 · Products
Header "Products" + "+ Add". Table with grouped header: **Recipe** (Ammonia, KCl, Rock dry, Rock wet, Sulphur, ACP) · **Composition** (N, P2O5, K2O, S) · **Footprint** (PCF) · **Agronomy** (Rate, Yield gain) · **Unit cost 2026** (read-only) · row action *Modify*. Search + filter chips (All, Phosfusion, Reference). 12 rows.

## S13 · Product editor (sheet 480 w)
Name · Family · Recipe table (t/t, price, USD/t) with "+ Add ingredient" · Composition (4 inputs + soft sum check) · Footprint · Agronomy · live **Unit cost** footer; Save/Cancel. "Recipe changed since v… Re-run?" appears on affected simulations after save.

## S14 · Uploads
Header "Uploads" + *Upload document* (primary). Amber `FlagBanner` D1. Table: Filename · Type (badge: Prices / Freight / Agro tests / Crop prices) · Upload date · File date · **Data through** · Status. Drop-zone row at top when dragging.

## S15 · Upload review (sheet 480 w)
Stages: *Reading…* → **What I found**: detected type, File date, Data through, series/rows, "Affects: TSP FOB price, DAP, MAP", warnings → *Use this data* (primary) · Cancel.

## S16 · Parameters
Sections: Defaults (Cost-plus margin 20 %, Full cost, Value share 33.3 %, Market share 5 %, Ramp year 2030) · Data (Freshness threshold 2 months, Stale after 30 days, Price type, Carbon market) · Appearance (theme). Each with description and "Reset to default".

## S17 · Command palette (⌘K)
Centered 560 `Command`: groups *Actions* (New simulation, Configure run, Upload document, Open memo), *Simulations*, *Products*, *Pages*. Footer key hints.

## S18 · Derived view (2025 conditions)
S05 with `DerivedBanner` and Conditions chip highlighted; KPIs/charts reflect 2025; "Across years" 2025 column outlined.

## S19 · Ask AI — staged change
Panel shows user "What if the value share is 50%?" → assistant text → **ChangeCard** (`Value share 33.3 % → 50 %` · "Value pricing 740.99 → 791.48 (preview)" · *Apply & re-run (v2)* · *Dismiss*).

## S20 · Dark mode dashboard
S05 in dark tokens (verifies greyscale chart ramp reversal).

---

## Mobile (second target)
| ID | Screen |
|---|---|
| M01 | Home: composer bottom-anchored, chips horizontal scroll, ☰ drawer |
| M02 | Thread with ResultCard and question chips |
| M03 | Run form bottom sheet |
| M04 | Simulation Dashboard: pivot chips scroll, KPI stack, ladder, swipeable charts, flags accordion, floating "Ask AI" pill |
| M05 | Ask AI full-screen view |
| M06 | Pricing method cards (stacked) |
| M07 | Margin table as cards |
| M08 | Memo bottom sheet |
