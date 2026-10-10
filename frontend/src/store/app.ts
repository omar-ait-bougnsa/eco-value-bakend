import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Parameters, Product, RefId, Run, RunInput, Snapshot, UploadFile } from '@/engine/types'
import { setPeriodData, type Period, type PeriodPreset } from '@/engine/period'
import { toast } from 'sonner'
import { api, report, type Freshness, type Ingredient, type Job, type Limits, type Outlook, type SimRecord } from '@/lib/api'
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
  ingredients: Ingredient[]
  range: Period
  presets: PeriodPreset[]
  freshness: Freshness
  /** The server's validation limits, for the forms. */
  limits: Limits
  /** Requests the backend agent suggests: on the home page (`start`) and once a simulation has a run (`next`). */
  prompts: { start: string[]; next: string[]; supported: { label: string; example: string }[] }
  /** Goes up when the products, parameters or uploads change: what the backend calculated from them is asked again. */
  rev: number
  ui: AppUI
  local: Record<string, Local>
  load: () => Promise<void>
  refreshFreshness: () => Promise<void>
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
  /** The agent job of a simulation, as the server reports it. */
  setJob: (simId: string, job: Job | null) => void
  addRun: (simId: string, input: RunInput, by: Run['createdBy'], summary: string) => Promise<Run>
  syncRuns: (simId: string) => Promise<Run[]>
  upsertProduct: (p: Product, isNew: boolean) => Promise<Product>
  addUpload: (file: File) => Promise<UploadFile>
  reset: () => Promise<void>
}

/** The view of a simulation: on its run's input, or on the backend's default input before a first run. */
export function makeView(over: Partial<SimView> = {}, input?: RunInput, base: RunInput = useApp.getState().defaultInput): SimView {
  const i = input ?? base
  return { tab: 'costing', period: { from: i.periodFrom, to: i.periodTo }, ref: i.referenceId, pin: 'product', version: 1, product: i.productIds[0], strategy: 'all', metric: 'price', ...over }
}

/** A backend simulation joined with its local thread and view. Without a local thread, the latest run is shown as its start. */
function toSim(rec: SimRecord, base: RunInput, local?: Local): Simulation {
  const last = rec.runs[rec.runs.length - 1]
  const thread: Msg[] = local?.thread ?? (last ? [
    { id: uid(), kind: 'text', text: summaryText(last) },
    { id: uid(), kind: 'result', version: last.version },
  ] : [])
  return { ...rec, thread, view: local?.view ?? makeView({ version: last?.version ?? 1 }, last?.input, base) }
}

/** The dialogs and side sheets. */
const MODALS = ['commandOpen', 'runFormOpen', 'memoOpen', 'hypothesesOpen', 'productSheetId', 'uploadReviewOpen'] as const

const freshUI = (): AppUI => ({ theme: 'system', sidebarOpen: true, askOpen: true, commandOpen: false, runFormOpen: false, memoOpen: false, hypothesesOpen: false, productSheetId: null, uploadReviewOpen: false, compareWith: null, dirty: false })

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
      ingredients: [],
      range: { from: '', to: '' },
      presets: [],
      freshness: { latest: null, through: null, warn: false, d1: null, d2: null, behind: {} },
      limits: {} as Limits,
      prompts: { start: [], next: [], supported: [] },
      rev: 0,
      ui: freshUI(),
      local: {},
      load: async () => {
        set({ status: 'loading', error: null })
        try {
          const [products, snapshots, uploads, params, records, defaultParams, defaultInput, outlook, ingredients, range, presets, freshness, prompts, limits] = await Promise.all([api.products(), api.snapshots(), api.uploads(), api.params(), api.sims(), api.defaultParams(), api.defaultInput(), api.outlook(), api.ingredients(), api.range(), api.presets(), api.freshness(), api.agentPrompts(), api.limits()])
          setPeriodData(range, presets)
          const { local, sims: open } = get()
          const sims = Object.fromEntries(records.map((r) => [r.id, toSim(r, defaultInput, open[r.id] ?? local[r.id])]))
          set((s) => ({ status: 'ready', products, snapshots, uploads, params, defaultParams, defaultInput, outlook, ingredients, range, presets, freshness, prompts, limits, rev: s.rev + 1, sims, order: records.map((r) => r.id) }))
        } catch (e) {
          set({ status: 'error', error: e instanceof Error ? e.message : String(e) })
        }
      },
      setUI: (p) => set((s) => {
        // One dialog at a time: opening one closes the others. A form with unsaved changes keeps its place until it is saved or closed.
        const opening = MODALS.some((k) => p[k] && !s.ui[k])
        if (!opening) return { ui: { ...s.ui, ...p } }
        const others = MODALS.filter((k) => s.ui[k] && !(k in p))
        if (others.length && s.ui.dirty) { toast('Save or close the open form first', { description: 'It has changes that are not saved.' }); return s }
        const closed = Object.fromEntries(others.map((k) => [k, k === 'productSheetId' ? null : false]))
        return { ui: { ...s.ui, ...closed, ...p, dirty: false } }
      }),
      refreshFreshness: async () => {
        const freshness = await api.freshness()
        set({ freshness })
      },
      setParams: (p) => {
        set((s) => ({ params: { ...s.params, ...p } }))
        // On a rejected value, show why and go back to what the backend holds.
        api.patchParams(p)
          .catch((e) => { report(e); return api.params().then((params) => set({ params })) })
          .then(() => { set((s) => ({ rev: s.rev + 1 })); return get().refreshFreshness() })
          .catch(report)
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
        set((s) => ({ sims: { ...s.sims, [rec.id]: toSim(rec, s.defaultInput, src && { thread: src.thread, view: src.view }) }, order: [rec.id, ...s.order] }))
        return rec.id
      },
      setView: (id, v) => set((s) => (s.sims[id] ? { sims: { ...s.sims, [id]: { ...s.sims[id], view: { ...s.sims[id].view, ...v } } } } : s)),
      pushMsg: (simId, m) => { set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], thread: [...s.sims[simId].thread, m] } } } : s)); return m.id },
      patchMsg: (simId, msgId, patch) => set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], thread: s.sims[simId].thread.map((m) => (m.id === msgId ? ({ ...m, ...patch } as Msg) : m)) } } } : s)),
      setJob: (simId, job) => set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], job } } } : s)),
      setBusy: (simId, b) => set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], busy: b } } } : s)),
      addRun: async (simId, input, by, summary) => {
        const run = await api.addRun(simId, input, by, summary)
        set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], runs: [...s.sims[simId].runs, run], view: { ...s.sims[simId].view, version: run.version, period: { from: input.periodFrom, to: input.periodTo }, ref: input.referenceId, product: input.productIds[0] } } } } : s))
        return run
      },
      // Runs the backend agent saved (a pricing run, an applied change) are read back from it.
      syncRuns: async (simId) => {
        const { runs, title, job } = await api.sim(simId) // the agent names a simulation after its first run
        const last = runs[runs.length - 1]
        set((s) => (s.sims[simId] ? { sims: { ...s.sims, [simId]: { ...s.sims[simId], runs, title, job: job ?? s.sims[simId].job, view: last ? { ...s.sims[simId].view, version: last.version, period: { from: last.input.periodFrom, to: last.input.periodTo }, ref: last.input.referenceId, product: last.input.productIds[0] } : s.sims[simId].view } } } : s))
        return runs
      },
      upsertProduct: async (p, isNew) => {
        const saved = await (isNew ? api.createProduct(p) : api.updateProduct(p))
        set((s) => ({ rev: s.rev + 1, products: s.products.some((x) => x.id === saved.id) ? s.products.map((x) => (x.id === saved.id ? saved : x)) : [...s.products, saved] }))
        return saved
      },
      addUpload: async (file) => {
        const saved = await api.addUpload(file)
        set((s) => ({ rev: s.rev + 1, uploads: [saved, ...s.uploads.filter((u) => u.id !== saved.id)] })) // a file already there is not listed twice
        await get().refreshFreshness().catch(report)
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
        ui: { ...s.ui, commandOpen: false, runFormOpen: false, memoOpen: false, hypothesesOpen: false, productSheetId: null, uploadReviewOpen: false, dirty: false },
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

/** Products a run can be priced against: the backend's `reference` family. */
export const useReferences = () => { const products = useApp((s) => s.products); return products.filter((p) => p.family === 'reference').map((p) => p.id as RefId) }
