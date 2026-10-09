# 07 · Tech Spec

## 1. Stack
| Concern | Choice |
|---|---|
| Build | **Vite 6 + React 18 + TypeScript** (strict) |
| Styling | **Tailwind CSS v4** + CSS variables (shadcn tokens, doc 05) |
| UI kit | **shadcn/ui** (zinc) + **prompt-kit** components (copied via registry into `src/components/prompt-kit`) |
| Routing | `react-router-dom` v6 (data router) |
| State | **Zustand** (+ `persist` to `localStorage`, versioned key `evs.v1`) |
| Charts | Recharts via shadcn `chart` |
| Forms | `react-hook-form` + `zod` |
| Icons | `lucide-react` |
| Fonts | `geist` (Sans + Mono) |
| Markdown | `react-markdown` (prompt-kit `Markdown`) |
| Export | `jspdf` + `html2canvas` (PDF memo), `xlsx` (SheetJS) for numbers, Blob download for Markdown |
| Tests | **Vitest** (engine golden tests, agent routing) + **Playwright** smoke (hero path) |
| Lint | ESLint + Prettier |

No backend. All data seeded in `src/data`. LLM optional via `VITE_OPENROUTER_API_KEY` (env only).

## 2. Folder structure
```
eco-value-simulator/
  docs/                      # this spec pack
  src/
    main.tsx  App.tsx  routes.tsx
    styles/globals.css       # tokens
    lib/ { utils.ts, format.ts, ids.ts, export/ }
    data/ { products.ts, snapshots.ts, uploads.ts, parameters.ts, seed-simulations.ts }
    engine/ { types.ts, cost.ts, methods.ts, margin.ts, volume.ts, carbon.ts, run.ts, flags.ts, compare.ts, index.ts, __tests__/ }
    agent/ { intents.ts, script.ts, tools.ts, memo.ts, llm.ts, types.ts, __tests__/ }
    store/ { simulations.ts, products.ts, uploads.ts, parameters.ts, ui.ts }
    components/
      ui/                    # shadcn
      prompt-kit/            # prompt-kit
      app/ { AppSidebar, CommandPalette, FreshnessChip, ThemeToggle, ... }
      sim/ { PriceLadder, KpiCard, PivotBar, VersionChip, ProvenanceBadge, FlagRow, FlagBanner,
             ResultCard, ChangeCard, DerivedBanner, MethodCard, RecipeTable, charts/* }
    pages/ { Home, Simulation (tabs/*), Products, Uploads, Parameters }
    dialogs/ { RunForm, MemoSheet, ProductSheet, UploadReviewSheet }
  tests/e2e/hero.spec.ts
```

## 3. Engine architecture
- Pure functions, no I/O, no React. `runEngine(input: RunInput, ctx: {products, snapshots}) → RunOutput` returns per-product/per-method prices, cost breakdown, margins, volume, waterfall, carbon scenarios, flags.
- Deterministic; **golden tests** assert doc 03 §4 values to 2 decimals.
- Derived views (`snapshot_view`) call `runEngine` with a different snapshot; never persist.
- Flags derived by `flags.ts` from `RunInput + sources + uploads`.

## 4. State model (Zustand)
```ts
simulations: { byId, order }          // Simulation { runs[], thread[] }
activeRun(simId) -> Run               // via ?run=
ui: { sidebarOpen, askAiOpen, theme, commandOpen }
products, uploads, parameters         // seeded, editable
actions: createSimulation, appendMessage, applyChange(patch) -> new Run, resolveFlag, ...
```
Runs are append-only. `applyChange` clones the previous RunInput, applies a patch, records `changeSet` and `createdBy`, runs the engine, and pushes `Run vN+1`.

## 5. Agent runtime
- `agent/script.ts` is an async generator yielding thread events (`step`, `flag`, `question`, `tool`, `result`, `text`). The UI streams them with delays (80–600 ms) to feel live.
- `intents.ts` routes free text (regex, EN/FR) to scripts; fallback to `llm.ts` (OpenRouter `/chat/completions`, tool-grounded context, `model` from `VITE_OPENROUTER_MODEL`) when a key exists, else capability reply.
- Numbers in messages are injected from run objects via template tokens (`{{run.v1.anchor}}`) — no LLM-typed numbers in scripted paths.

## 6. Routing & URL state
`/` Home · `/s/:id` Simulation (query: `tab`, `run`, `cond`, `ref`, `pin`) · `/products` · `/uploads` · `/parameters`. Query params are the source of truth for view state so any view is shareable by URL.

## 7. Performance & quality
- Engine runs < 5 ms; memoize by input hash.
- Code-split pages; charts lazy-loaded.
- Accessibility: Radix primitives via shadcn; `aria-live` on streaming steps.
- Type safety: engine types shared with UI; `zod` schemas for forms/uploads.

## 8. Build & scripts
```
pnpm dev | build | preview | test | test:e2e | lint
```
Env: `.env.example` documents `VITE_OPENROUTER_API_KEY`, `VITE_OPENROUTER_MODEL` (optional).

## 9. Risks
| Risk | Mitigation |
|---|---|
| prompt-kit registry install fails | Components are plain shadcn-style source files — vendor copies are acceptable |
| LLM unavailable offline | Scripted agent covers the hero path |
| Jsdom charts flaky | Test engine/agent in node; smoke e2e only for UI |
| PDF export fidelity | Render memo from a print-styled DOM node |
