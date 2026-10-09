# 02 · Information Architecture & Flows

## 1. Sitemap

```
/                          Chat home (new simulation)
/s/:simId                  Simulation page (+ Ask AI panel). Opens as soon as a run starts.
  view state: tab=costing|pricing|margin|overview · run=v2 · period · ref=TSP · pin=product|strategy|metric
/products                  Products library (table + side sheet editor)
/uploads                   Uploads (table + review sheet)
/parameters                Global defaults
```

Global overlays: **Command palette (⌘K)**, **Run form (dialog)**, **Memo (sheet)**, **Hypotheses (drawer)**, **Product editor (sheet)**, **Upload review (sheet)**.

## 2. Navigation (left sidebar, shadcn `Sidebar`, collapsible ⌘B)

```
[Logo / wordmark: Eco Value Simulator]
[+ New simulation]            ⌘⇧O  → /
[Search                ⌘K]
History
  Today / Yesterday / Previous 7 days / Older
    ● Phosfusion 65-35 vs TSP          (dot = open flags; ⋯ rename · duplicate · delete)
Library
  Products
  Uploads                              (amber dot if freshness warning)
Parameters
[User menu: theme toggle · shortcuts]
```

Rules:
- Selected route has the subtle `bg-accent` row. History items truncate with ellipsis.
- Sidebar width 260 (≥1280), icon-rail 56 (1024–1279), drawer (<1024).
- Footer of Home composer: **Freshness chip** — `Latest upload · 02 Oct 2026 · Data through 24 Sep` → amber when stale/discrepant; click → /uploads.

## 3. Simulation page anatomy (≥1280)

```
┌ Sidebar ┬──────────────────────── Main ────────────────────────┬─ Ask AI ─┐
│         │ Header: title ▸ v2 ▾ · Hypotheses (quiet link) ·       │ thread   │
│         │   Analysis period ▾ · Compare to: TSP ▾ · Memo · Export│ (same    │
│         │ Pivot bar: [Product ●pinned] [Strategy] [Metric]       │ convers.)│
│         │ Tabs: Costing · Pricing · Margin · Overview            │ composer │
│         │ ─────────────────────────────────────────────────────  │          │
│         │ Tab content (+ flags rail on Dashboard)                │          │
└─────────┴────────────────────────────────────────────────────────┴──────────┘
```
Ask AI panel: 380 px, resizable 320–560, toggle ⌘/. Below 1280 it is an overlay; on mobile a full-screen view.

## 4. Key flows

### F-A · Run from chat (hero)
`Home → type/click suggestion → redirect immediately to /s/:id (skeleton page + Ask AI panel streams Steps) → (question chip → user answers) → the page fills in (Costing tab) with the result card in the panel`

### F-B · Run from form
`Composer ⚙ Configure run → dialog (Essentials, Advanced) → freshness line → Run → same thread flow as F-A`

### F-C · What-if
`Ask AI: "What if value share is 50%?" → agent staged-change card (33% → 50%) → Apply & re-run (v2) → page updates, version chip v2, compare available. Manual edits: Hypotheses drawer → staged bar → Re-run.`

### F-D · Resolve a flag
`Dashboard flags rail → click flag → opens relevant place (Hypotheses row highlighted, or answer chips in thread) → resolving creates a new run (v+1) and marks the flag resolved`

### F-E · Change conditions / compare
`Analysis period ▾ (preset or custom range) → derived-view banner → Across-years strip highlights the covered years → "Back to the run's period"`

### F-F · Upload data
`Uploads → Upload document (type or auto-detect) → Reading… → "What I found" sheet (type, File date, Data through, series count, affected inputs, warnings) → Use this data → row added, chip updates; discrepancy banner if gap ≥ threshold`

### F-G · Edit a product
`Products → Modify (or + Add) → side sheet: recipe table (+ Add ingredient), composition, footprint, agronomy → live unit cost → Save → affected simulations show "Recipe changed since vN · Re-run?"`

### F-H · Memo & export
`Memo button → sheet (follows version chip) → Export ▾ (PDF · Markdown · xlsx)`

## 5. State inventory (per surface)

| Surface | Empty | Loading | Partial | Error | Stale |
|---|---|---|---|---|---|
| Home | greeting + chips | — | — | agent unavailable banner | freshness chip amber |
| Thread | — | `Steps` + `TextShimmer` | question pending (chips) | tool failure `SystemMessage` + Retry | — |
| Dashboard | "Run a simulation" | skeleton cards/charts | market tick "Add benchmark"; carbon chart "Add a carbon price" | engine error panel | derived-view banner |
| Pricing | — | skeleton | method card "Needs input" | — | banner |
| Products | no products → "+ Add" | skeleton rows | cost "—" if input missing | save error toast | "Recipe changed" |
| Uploads | drop zone | Reading… | warnings in review sheet | unreadable file panel | discrepancy banner |

## 6. Flag model (shared across surfaces)

`severity: error | warning | info | resolved` · `scope: input | source | method | data` · `owner: agent`.
Display: icon + text always (never color only); amber = warning, red = error, grey = info/resolved.
Flags are listed on the Dashboard rail, inline on the affected input/method, and as `SystemMessage` in the thread. Each flag has an action: *Answer*, *Open input*, *Add benchmark*, *Dismiss (assume)*.

## 7. Keyboard & shortcuts

⌘K palette · ⌘B sidebar · ⌘/ Ask AI · ⌘⇧O new simulation · ⌘⏎ send/run · `[` `]` previous/next tab · `Esc` closes sheets.
