# 08 · Figma & Build Plan

## 1. Figma file
`https://www.figma.com/design/vwGKCMMQ4RkPcFL3WJzRz4/Untitled` — build **desktop** frames (1440×900) first, mobile second.

### Pages
1. `Cover & Tokens` — palette, type scale, spacing, components sheet
2. `Desktop` — S01–S20
3. `Mobile` — M01–M08

### Frame inventory (Desktop)
| Frame | Spec | Notes |
|---|---|---|
| 00 Tokens & components | doc 05 | variables for light/dark, text styles |
| S01 Home | doc 06 | |
| S02 Thread — question | | |
| S03 Thread — result card | | |
| S04 Run form | | dialog over S01 scrim |
| S05 Dashboard | | hero frame |
| S06 Hypotheses | | |
| S07 Pricing | | |
| S08 Costing | | |
| S09 Margin | | |
| S10 Versions & compare | | |
| S11 Memo sheet | | |
| S12 Products | | |
| S13 Product editor | | |
| S14 Uploads | | |
| S15 Upload review | | |
| S16 Parameters | | |
| S17 Command palette | | |
| S18 Derived view | | |
| S19 Staged change | | |
| S20 Dashboard dark | | |

### Build order
Tokens → shared shell (sidebar, header, composer, chips) → S01 → S02/S03 → S05 (+ladder, KPIs, charts) → S06–S09 → S10–S11 → S12–S16 → S17–S20 → mobile.

### Conventions
- Local variables (light/dark modes) bound to fills/strokes; text styles for the type scale.
- Auto-layout everywhere; real component set for Button, Badge, KPI card, Flag row, Method card, Ladder (variants).
- Name frames `S05 · Simulation — Dashboard`. Group deliverables in sections.

## 2. App build plan
| Phase | Deliverable | Done when |
|---|---|---|
| P0 | Vite scaffold, Tailwind v4, shadcn init, prompt-kit components, tokens | `pnpm dev` renders shell in both themes |
| P1 | Seed data + engine + golden tests | tests pass for doc 03 §4 |
| P2 | Shell: sidebar, routing, ⌘K, theme, freshness chip | navigation works |
| P3 | Home + thread + scripted agent + RunForm | hero path to ResultCard |
| P4 | Simulation page: Dashboard, charts, PriceLadder, pivot/version/conditions | S05/S18 match Figma |
| P5 | Hypotheses (staged edits), Pricing, Costing, Margin | S06–S09 |
| P6 | Versions + compare, ChangeCard, flags resolution | F-C, F-D |
| P7 | Memo + export | F-H |
| P8 | Products + editor, Uploads + review, Parameters | F-F, F-G |
| P9 | Mobile responsive pass | M01–M08 |
| P10 | Playwright hero test, a11y pass, polish | green CI-style run |

## 3. Definition of done (demo)
- Hero story completes in < 3 min with no console errors.
- All 20 desktop screens reachable from the UI.
- Golden numbers visible exactly as in doc 03 §4.
- Light + dark; keyboard shortcuts work; mobile core loop usable.
