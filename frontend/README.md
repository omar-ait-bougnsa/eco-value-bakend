# Eco Value Simulator

Chat-first pricing & margin simulator for new OCP fertilizers (AgentX · Nutricrops · Eco Value). Demo hero: **Phosfusion 65-35 vs TSP**.

> The agent gathers, checks and explains. The engine calculates with validated formulas. People decide.

Design: [Figma desktop frames](https://www.figma.com/design/vwGKCMMQ4RkPcFL3WJzRz4/Untitled) (S01–S20 + tokens).

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # engine golden values + scripted-agent hero path (13 tests)
npm run build
```

Optional LLM fallback for unrecognised questions: copy `.env.example` to `.env` and set `VITE_OPENROUTER_API_KEY`. The hero flow needs no key.

## 3-minute demo script

1. Home → click **Price Phosfusion 65-35 against TSP**.
2. The agent streams its steps, flags that prices (21 Apr) are 5 months older than freight (24 Sep), and asks which TSP cost to use (494 deck vs 655.18 workbook). Pick **Use 655.18**.
3. Result card: anchor **313.91 USD/t**, CGM **3.02** vs TSP **−15.18**, anchor below the cost-plus floor (373.08). Click **Open simulation**.
4. Dashboard: KPIs, price ladder, flags, four charts. Browse Hypotheses · Pricing · Costing · Margin. Try the pivot bar (pin Product / Strategy / Metric).
5. Ask AI → **What if the value share is 50%?** → **Apply & re-run** → v2 (value 740.99 → 791.48). Open the version chip → **Compare with v1**.
6. Header **Conditions → 2025**: derived view (sulphur 299, not 900 → anchor now clears the floor).
7. **Memo** → Export (PDF / Markdown / xlsx).
8. **Uploads → Upload newer prices → sample file → Use this data**: the discrepancy flag resolves.
9. **Products → Modify**: edit a recipe, watch the unit cost update live.

User menu (bottom-left): theme, **Reset demo data**. Shortcuts: ⌘K palette · ⌘B sidebar · ⌘/ Ask AI · ⌘N new simulation · ⌘⇧R Configure run.

## Stack

Vite · React 19 · TypeScript · Tailwind v4 · shadcn/ui (zinc) · prompt-kit (chat) · Zustand · custom SVG charts · Vitest.

## Docs

Spec pack in [`docs/`](docs/README.md): product, IA & flows, engine (formulas traced to workbook cells), agent, design system, screens, tech, Figma plan.

## Notes

- Engine: `src/engine` (pure TS). Seed data from `Pricing model.xlsx` and the CRU price files: `src/data`.
- All numbers on screen come from the engine; the scripted agent only quotes them.
- Data is seeded; "Upload" simulates parsing and detection, it does not ingest the file's contents.
