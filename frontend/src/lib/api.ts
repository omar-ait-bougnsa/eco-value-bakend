import { toast } from 'sonner'
import type { CostLine, Flag, IngredientId, Parameters, Product, Run, RunInput, RunOutput, Snapshot, UploadFile } from '@/engine/types'
import type { Period, PeriodPreset } from '@/engine/period'

// In development Vite proxies /api to the backend (vite.config.ts). Set VITE_API_URL to call it directly.
const BASE = (import.meta.env?.VITE_API_URL as string | undefined) ?? '/api'

export interface Outlook { years: number[]; ammonia: number[]; kcl: number[]; sulphur: number[] }
/** A turn of the agent, with the state the server stored for it. */
export interface Job {
  id: string
  simulationId: string
  kind: 'message' | 'run' | 'answer'
  state: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timed_out'
  mode: 'llm' | 'script' | null
  /** What was asked: sent again to retry. */
  request: { text: string; input?: RunInput; answer?: AgentAnswer }
  result: { outcome: 'run' | 'question' | 'change' | 'answer' | 'unsupported'; runVersion: number | null } | null
  failureCode: string | null
  error: string | null
  transitions: { state: Job['state']; at: string }[]
  createdAt: string
  startedAt: string | null
  finishedAt: string | null
  timeoutSeconds: number
}
export const jobEnded = (j: Job | null | undefined) => !!j && j.state !== 'queued' && j.state !== 'running'
export interface SimRecord { id: string; title: string; createdAt: string; runs: Run[]; job?: Job | null }
export interface Ingredient { id: IngredientId; label: string }
/** Latest upload and the data-freshness flags. `behind`: Argus price files too old against freight (upload id → months). */
export interface Freshness { latest: UploadFile | null; through: UploadFile | null; warn: boolean; d1: Flag | null; d2: Flag | null; behind: Record<string, number> }
/** Raw-material cost of a recipe at the input prices of a period. */
export interface RecipeCost { snapshotId: string; snapshotLabel: string; periodFrom: string; periodTo: string; asOf: string; source: string; lines: CostLine[]; /** Null when a price is missing: see `unavailable`. */ rawMaterial: number | null; unavailable: string | null }
/** Market data of an analysis period: the yearly snapshots blended by days. */
export interface ResolvedSnapshot { period: Period; label: string; weights: Record<string, number>; snapshot: Snapshot }
export interface EngineResult { input: RunInput; output: RunOutput }
export interface InputChange { key: string; before: unknown; after: unknown }
export interface UploadDetection { name: string; size: string; type: UploadFile['type']; typeLabel: string; fileDate: string; dataThrough: string; series: string; affects: string[]; resolves: boolean; warn?: string | null; /** Why the file would be refused. */ problems: string[]; /** The upload that already holds this exact file. */ duplicateOf?: string | null }
/** Whether the backend agent has a model to call ('llm') or only its scripted fallback ('script'). */
export interface AgentStatus {
  mode: 'llm' | 'script'
  provider: string | null
  model: string | null
  configured: boolean
  enabled: boolean
  /** Why the rule-based assistant answers instead of a model. Null when a model does. */
  fallbackReason: 'disabled' | 'no_api_key' | 'recent_failure' | 'budget_exhausted' | null
  label: string
  capabilities: string
  budget: { spent_usd: number; cap_usd: number; remaining_usd: number }
}
/** Business limits of the inputs, as the server enforces them (GET /limits). The forms show them; the server decides. */
export interface Limits { productNameMin: number; productNameMax: number; recipeQtyMax: number; recipeTotalMax: number; nutrientTotalMax: number; pcfMax: number; appRateMax: number; yieldGainMaxTHa: number; yieldGainMaxPct: number; baselineYieldMax: number; priceMax: number; marginMax: number; marketingMax: number; addressableMax: number; rampYearSpan: number; uploadMaxBytes: number }
export interface FieldProblem { field: string; message: string }
/** A request the server refused, with what is wrong field by field when it said so. */
export class ApiError extends Error {
  fields: FieldProblem[]
  constructor(message: string, fields: FieldProblem[] = []) { super(message); this.fields = fields }
}
export interface Sensitivity { variable: string; points: { sulphurPrice: number; cgmNew: number | null; cgmRef: number | null; deltaCgm: number | null }[]; breakEvens: { productId: string; sulphurPrice: number | null; kind: 'zero_margin' | 'crossover'; note: string }[] }
/** A passage of an indexed document, with where it comes from (backend RAG.md). */
export interface Passage { passage: string; source: string; date: string | null; page: number | null; pageEnd: number | null; section: string | null; docType: string; relevanceScore: number; documentId: string; chunkId: string }
export interface KnowledgeDocument { id: string; name: string; title: string; type: string; date: string | null; pages: number | null; chunks: number; status: 'indexing' | 'ready' | 'failed'; error: string | null; uploadId: string | null; seeded: boolean }
/** One event of an agent turn (backend agent.md, 7.2). */
export type AgentEvent =
  | { type: 'step'; payload: { label: string; status: 'running' | 'done' } }
  | { type: 'tool'; payload: { name: string; label: string; latencyMs: number } }
  | { type: 'flag'; payload: Flag }
  | { type: 'question'; payload: { text: string; options: { id: string; label: string; sub?: string | null; primary?: boolean }[]; flag?: string; resume?: Record<string, unknown>; summary?: string } }
  | { type: 'result'; payload: { runId: string; version: number } }
  | { type: 'change'; payload: { id: string; label: string; reason: string; patch: Partial<RunInput>; before: Record<string, unknown>; after: Record<string, unknown>; previews?: { label: string; before: string; after: string }[] } }
  | { type: 'citation'; payload: { index: number; label: string; source: string; passage: string } }
  | { type: 'text'; payload: { content: string; sources?: string[]; code?: string; suggestions?: { label: string; example: string }[] } }
  | { type: 'job'; payload: Job }
  | { type: 'view'; payload: { period?: Period; tab?: 'costing' | 'pricing' | 'margin' | 'overview'; memo?: boolean } }
  | { type: 'suggest'; payload: { items: string[] } }
  | { type: 'error'; payload: { message: string; code?: string; fatal?: boolean; recoverable?: boolean } }
  | { type: 'done'; payload: { mode: 'llm' | 'script' } }

async function failure(res: Response) {
  const body = await res.json().catch(() => null)
  const detail = typeof body?.detail === 'string' ? body.detail : res.statusText
  return new ApiError(detail || `Request failed (${res.status})`, Array.isArray(body?.errors) ? body.errors : [])
}

async function send(path: string, init: RequestInit) {
  let res: Response
  try {
    res = await fetch(BASE + path, init)
  } catch {
    throw new Error('Cannot reach the backend. Is it running?')
  }
  if (!res.ok) throw await failure(res)
  return res
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData
  const res = await send(path, { method, headers: body && !form ? { 'Content-Type': 'application/json' } : undefined, body: form ? body : body ? JSON.stringify(body) : undefined })
  return res.status === 204 ? (undefined as T) : res.json()
}

/** The option picked on a question of the agent, with what that question gave to resume from. */
export interface AgentAnswer { option: string; question: string; resume?: Record<string, unknown>; summary?: string }
/** Sent with a message instead of leaving the agent to read its text: a run input to price (Configure run), or the answer to its question. */
export interface TurnExtra { input?: RunInput; answer?: AgentAnswer }

/** Send a message to the backend agent. The turn comes back as Server-Sent Events; `on` gets them one at a time, in order. */
async function agentTurn(simId: string, text: string, on: (e: AgentEvent) => void | Promise<void>, extra: TurnExtra = {}) {
  const res = await send(`/simulations/${simId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, ...extra }) })
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    const frames = (buf + (value ?? '')).split(/\r?\n\r?\n/)
    buf = done ? '' : frames.pop()! // the last piece is an unfinished event, until the stream ends
    for (const f of frames) {
      const data = f.split(/\r?\n/).find((l) => l.startsWith('data:'))
      if (data) await on(JSON.parse(data.slice(5)))
    }
    if (done) return
  }
}

const span = (p: Period) => `periodFrom=${p.from}&periodTo=${p.to}`

export const api = {
  products: () => req<Product[]>('GET', '/products'),
  createProduct: ({ id: _id, status: _s, issues: _i, ...p }: Product) => req<Product>('POST', '/products', p),
  updateProduct: ({ id, status: _s, issues: _i, ...p }: Product) => req<Product>('PUT', `/products/${encodeURIComponent(id)}`, p),
  snapshots: () => req<Snapshot[]>('GET', '/snapshots'),
  params: () => req<Parameters>('GET', '/parameters'),
  defaultParams: () => req<Parameters>('GET', '/parameters/defaults'),
  defaultInput: () => req<RunInput>('GET', '/parameters/default-run-input'),
  outlook: () => req<Outlook>('GET', '/outlook'),
  ingredients: () => req<Ingredient[]>('GET', '/ingredients'),
  range: () => req<Period>('GET', '/periods/range'),
  presets: () => req<PeriodPreset[]>('GET', '/periods/presets'),
  resolveSnapshot: (p: Period) => req<ResolvedSnapshot>('GET', `/snapshots/resolve?${span(p)}`),
  productCost: (id: string, p?: Period) => req<RecipeCost>('GET', `/products/${encodeURIComponent(id)}/cost${p ? `?${span(p)}` : ''}`),
  recipeCost: (recipe: Product['recipe']) => req<RecipeCost>('POST', '/products/recipe-cost', { recipe }),
  limits: () => req<Limits>('GET', '/limits'),
  /** What saving this product would reject, field by field: the server's own rules, nothing saved. */
  validateProduct: ({ id: _id, status: _s, issues: _i, ...p }: Product, id?: string) => req<{ errors: FieldProblem[] }>('POST', `/products/validate${id ? `?id=${encodeURIComponent(id)}` : ''}`, p),
  validateRun: (input: Partial<RunInput>) => req<{ errors: FieldProblem[] }>('POST', '/engine/validate', input),
  freshness: () => req<Freshness>('GET', '/uploads/freshness'),
  /** The engine on an input, without saving a run: derived views and previews. */
  engineRun: (input: Partial<RunInput>) => req<EngineResult>('POST', '/engine/run', input),
  diffInputs: (before: RunInput, after: RunInput) => req<InputChange[]>('POST', '/engine/diff', { before, after }),
  patchParams: (p: Partial<Parameters>) => req<Parameters>('PATCH', '/parameters', p),
  uploads: () => req<UploadFile[]>('GET', '/uploads'),
  detectUpload: (file: File) => { const f = new FormData(); f.append('file', file); return req<UploadDetection>('POST', '/uploads/detect', f) },
  /** The record is made by the server from the file itself. The same file sent again returns the upload it already is (`duplicate`). */
  addUpload: (file: File) => { const f = new FormData(); f.append('file', file); return req<UploadFile>('POST', '/uploads', f) },
  sim: (id: string) => req<SimRecord>('GET', `/simulations/${id}`),
  sims: async () => Promise.all((await req<{ id: string }[]>('GET', '/simulations')).map((s) => api.sim(s.id))),
  createSim: (title: string) => req<SimRecord>('POST', '/simulations', { title }),
  renameSim: (id: string, title: string) => req<SimRecord>('PATCH', `/simulations/${id}`, { title }),
  deleteSim: (id: string) => req<void>('DELETE', `/simulations/${id}`),
  duplicateSim: (id: string) => req<SimRecord>('POST', `/simulations/${id}/duplicate`),
  addRun: (simId: string, input: RunInput, createdBy: Run['createdBy'], summary: string) => req<Run>('POST', `/simulations/${simId}/runs`, { input, replace: true, createdBy, summary }),
  sensitivity: (productId: string, referenceId: string) => req<Sensitivity>('POST', '/engine/sensitivity', { productId, referenceId }),
  searchKnowledge: (query: string, limit = 4) => req<{ results: Passage[]; model: string }>('POST', '/knowledge/search', { query, limit }),
  indexDocument: (file: File, uploadId?: string) => { const f = new FormData(); f.append('file', file); if (uploadId) f.append('uploadId', uploadId); return req<KnowledgeDocument>('POST', '/knowledge/documents', f) },
  agentStatus: () => req<AgentStatus>('GET', '/agent/status'),
  /** Requests the agent understands, with the workspace's own products: to start with, and once a simulation has a run. */
  agentPrompts: () => req<{ start: string[]; next: string[]; supported: { label: string; example: string }[] }>('GET', '/agent/prompts'),
  job: (id: string) => req<Job>('GET', `/jobs/${id}`),
  cancelJob: (id: string) => req<Job>('POST', `/jobs/${id}/cancel`),
  agentTurn,
  applyChange: (changeId: string, summary: string) => req<Run>('POST', `/changes/${changeId}/apply`, { summary }),
  dismissChange: (changeId: string) => req<void>('POST', `/changes/${changeId}/dismiss`),
  reset: () => req<void>('POST', '/reset'),
}

/** Show a failed request to the user. */
export function report(e: unknown) {
  toast.error(e instanceof Error ? e.message : 'Something went wrong')
}
