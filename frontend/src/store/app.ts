import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Ctx } from '@/engine/run'
import type { Parameters, Product, Run, RunInput, Snapshot, UploadFile } from '@/engine/types'
import { yearPeriod } from '@/engine/period'
import { api, report, type Outlook, type SimRecord, type UploadInput } from '@/lib/api'
import { summaryText } from '@/agent/memo'
import type { AppUI, Msg, Simulation, SimView } from './types'

let seq = 0
export const uid = (p = 'm') => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`

/** What stays in the browser for a simulation: the chat thread and the view. Everything else lives in the backend. */
type Local = Pick<Simulation, 'thread' | 'view'>

interface State {
  status: 'loading' | 'ready' | 'error'
  error: string | null
  sims: Record<string, Simulation>
  order: string[]
  products: Product[]
  snapshots: Snapshot[]
  uploads: UploadFile[]
  params: Parameters
  defaultParams: Parameters
  defaultInput: RunInput
  outlook: Outlook
  ui: AppUI
  local: Record<string, Local>
  load: () => Promise<void>
  // actions
  setUI: (p: Partial<AppUI>) => void
  setParams: (p: Partial<Parameters>) => void
  createSim: (title: string, input: RunInput) => Promise<string>
  renameSim: (id: string, title: string) => void
  deleteSim: (id: string) => void
  duplicateSim: (id: string) => Promise<string>
  setView: (id: string, v: Partial<SimView>) => void
  pushMsg: (simId: string, m: Msg) => string
  patchMsg: (simId: string, msgId: string, patch: Record<string, unknown>) => void
  setBusy: (simId: string, b: boolean) => void
  addRun: (simId: string, input: RunInput, by: Run['createdBy'], summary: string) => Promise<Run>
  syncRuns: (simId: string) => Promise<Run[]>
  upsertProduct: (p: Product, isNew: boolean) => Promise<Product>
  addUpload: (u: UploadInput) => Promise<UploadFile>
  reset: () => Promise<void>
}

export const ctxOf = (s: Pick<State, 'products' | 'snapshots' | 'uploads' | 'params'>): Ctx => ({ products: s.products, snapshots: s.snapshots, uploads: s.uploads, params: s.params })

export function makeView(over: Partial<SimView> = {}, input?: RunInput): SimView {
  return { tab: 'costing', period: input ? { from: input.periodFrom, to: input.periodTo } : yearPeriod(2026), ref: input?.referenceId ?? 'TSP', pin: 'product', version: 1, product: input?.productIds[0] ?? 'phos-65-35', strategy: 'all', metric: 'price', ...over }
}

/** A backend simulation joined with its local thread and view. Without a local thread, one is rebuilt from the latest run. */
function toSim(rec: SimRecord, local?: Local): Simulation {
  const last = rec.runs[rec.runs.length - 1]
  const thread: Msg[] = local?.thread ?? (last ? [
    { id: uid(), kind: 'user', text: rec.title.replace(/ vs /, ' against ') },
    { id: uid(), kind: 'tool', label: `Pricing engine · ${last.input.methods.length} methods · v${last.version}` },
    { id: uid(), kind: 'text', text: summaryText(last) },
    { id: uid(), kind: 'result', version: last.version },
  ] : [])
  return { ...rec, thread, view: local?.view ?? makeView({ version: last?.version ?? 1 }, last?.input) }
}

const freshUI = (): AppUI => ({ theme: 'system', sidebarOpen: true, askOpen: true, commandOpen: false, runFormOpen: false, memoOpen: false, hypothesesOpen: false, productSheetId: null, uploadReviewOpen: false, compareWith: null })

export const useApp = create<State>()(
  persist(
    (set, get) => ({
      status: 'loading',
      error: null,
      sims: {},
      order: [],
      products: [],
      snapshots: [],
      uploads: [],
      // Placeholders: nothing renders before load() has filled these from the backend.
      params: {} as Parameters,
      defaultParams: {} as Parameters,
      defaultInput: {} as RunInput,
      outlook: { years: [], ammonia: [], kcl: [], sulphur: [] },
      ui: freshUI(),
      local: {},
      load: async () => {
        set({ status: 'loading', error: null })
        try {
          const [products, snapshots, uploads, params, records, defaultParams, defaultInput, outlook] = await Promise.all([api.products(), api.snapshots(), api.uploads(), api.params(), api.sims(), api.defaultParams(), api.defaultInput(), api.outlook()])
          const { local, sims: open } = get()
          const sims = Object.fromEntries(records.map((r) => [r.id, toSim(r, open[r.id] ?? local[r.id])]))
          set({ status: 'ready', products, snapshots, uploads, params, defaultParams, defaultInput, outlook, sims, order: records.map((r) => r.id) })
        } catch (e) {
          set({ status: 'error', error: e instanceof Error ? e.message : String(e) })
        }
      },
      setUI: (p) => set((s) => ({ ui: { ...s.ui, ...p } })),
      setParams: (p) => {
        set((s) => ({ params: { ...s.params, ...p } }))
        // On a rejected value, show why and go back to what the backend holds.
        api.patchParams(p).catch((e) => { report(e); void api.params().then((params) => set({ params })) })
      },
      createSim: async (title, input) => {
        const rec = await api.createSim(title)
        set((s) => ({ sims: { ...s.sims, [rec.id]: { ...rec, thread: [], view: makeView({}, input) } }, order: [rec.id, ...s.order] }))
        return rec.id
      },
      renameSim: (id, title) => {
        set((s) => ({ sims: { ...s.sims, [id]: { ...s.sims[id], title } } }))
        api.renameSim(id, title).catch(report)
      },
      deleteSim: (id) => {
        set((s) => { const { [id]: _x, ...rest } = s.sims; void _x; return { sims: rest, order: s.order.filter((o) => o !== id) } })
        api.deleteSim(id).catch(report)
      },
      duplicateSim: async (id) => {
        const rec = await api.duplicateSim(id)
        const src = get().sims[id]
        set((s) => ({ sims: { ...s.sims, [rec.id]: toSim(rec, src && { thread: src.thread, view: src.view }) }, order: [rec.id, ...s.order] }))
        return rec.id
      },
      setView: (id, v) => set((s) => (s.sims[id] ? { sims: { ...s.sims, [id]: { ...s.sims[id], view: { ...s.sims[id].view, ...v } } } } : s)),
      pushMsg: (simId, m) => { set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], thread: [...s.sims[simId].thread, m] } } } : s)); return m.id },
      patchMsg: (simId, msgId, patch) => set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], thread: s.sims[simId].thread.map((m) => (m.id === msgId ? ({ ...m, ...patch } as Msg) : m)) } } } : s)),
      setBusy: (simId, b) => set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], busy: b } } } : s)),
      addRun: async (simId, input, by, summary) => {
        const run = await api.addRun(simId, input, by, summary)
        set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], runs: [...s.sims[simId].runs, run], view: { ...s.sims[simId].view, version: run.version, period: { from: input.periodFrom, to: input.periodTo }, ref: input.referenceId, product: input.productIds[0] } } } } : s))
        return run
      },
      // Runs the backend agent saved itself (a pricing run, an applied change) are read back from it.
      syncRuns: async (simId) => {
        const { runs } = await api.sim(simId)
        const last = runs[runs.length - 1]
        set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], runs, view: last ? { ...s.sims[simId].view, version: last.version, period: { from: last.input.periodFrom, to: last.input.periodTo }, ref: last.input.referenceId, product: last.input.productIds[0] } : s.sims[simId].view } } } : s))
        return runs
      },
      upsertProduct: async (p, isNew) => {
        const saved = await (isNew ? api.createProduct(p) : api.updateProduct(p))
        set((s) => ({ products: s.products.some((x) => x.id === saved.id) ? s.products.map((x) => (x.id === saved.id ? saved : x)) : [...s.products, saved] }))
        return saved
      },
      addUpload: async (u) => {
        const saved = await api.addUpload(u)
        set((s) => ({ uploads: [saved, ...s.uploads] }))
        return saved
      },
      reset: async () => {
        await api.reset()
        set({ sims: {}, order: [], local: {}, ui: freshUI() })
        await get().load()
      },
    }),
    {
      name: 'evs.v3',
      version: 3,
      partialize: (s) => ({
        local: { ...s.local, ...Object.fromEntries(Object.entries(s.sims).map(([id, x]) => [id, { thread: x.thread, view: x.view }])) },
        ui: { ...s.ui, commandOpen: false, runFormOpen: false, memoOpen: false, hypothesesOpen: false, productSheetId: null, uploadReviewOpen: false },
      }),
    },
  ),
)

/** Starting input of a new run: the backend's default input, with the fields that follow the parameters taken from `p`. */
export function defaultRunInput(p: Parameters, overrides: Partial<RunInput> = {}): RunInput {
  return {
    ...useApp.getState().defaultInput,
    referenceId: p.defaultReference, costPlusMargin: p.costPlusMargin, marketingPct: p.marketingPct, fullCost: p.fullCost, dnaPerTon: p.dnaPerTon,
    valueShare: p.valueShare, priceType: p.priceType, carbonMarket: p.carbonMarket, marketShare: p.marketShare, rampTargetYear: p.rampTargetYear,
    ...overrides,
  }
}

export const useCtx = () => {
  const products = useApp((s) => s.products); const snapshots = useApp((s) => s.snapshots); const uploads = useApp((s) => s.uploads); const params = useApp((s) => s.params)
  return { products, snapshots, uploads, params } as Ctx
}
