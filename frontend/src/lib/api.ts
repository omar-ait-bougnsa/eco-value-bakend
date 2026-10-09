import { toast } from 'sonner'
import type { Flag, Parameters, Product, Run, RunInput, Snapshot, UploadFile } from '@/engine/types'

// In development Vite proxies /api to the backend (vite.config.ts). Set VITE_API_URL to call it directly.
const BASE = (import.meta.env?.VITE_API_URL as string | undefined) ?? '/api'

export interface Outlook { years: number[]; ammonia: number[]; kcl: number[]; sulphur: number[] }
export interface SimRecord { id: string; title: string; createdAt: string; runs: Run[] }
export type UploadInput = Omit<UploadFile, 'id' | 'uploadedAt'>
export interface UploadDetection { name: string; size: string; type: UploadFile['type']; typeLabel: string; fileDate: string; dataThrough: string; series: string; affects: string[]; resolves: boolean; warn?: string | null }
/** Whether the backend agent has a model to call ('llm') or only its scripted fallback ('script'). */
export interface AgentStatus { mode: 'llm' | 'script'; budget: { spent_usd: number; cap_usd: number; remaining_usd: number } }
export interface Sensitivity { variable: string; points: { sulphurPrice: number; cgmNew: number | null; cgmRef: number | null; deltaCgm: number | null }[]; breakEvens: { productId: string; sulphurPrice: number | null; kind: 'zero_margin' | 'crossover'; note: string }[] }
/** A passage of an indexed document, with where it comes from (backend RAG.md). */
export interface Passage { passage: string; source: string; date: string | null; page: number | null; pageEnd: number | null; section: string | null; docType: string; relevanceScore: number; documentId: string; chunkId: string }
export interface KnowledgeDocument { id: string; name: string; title: string; type: string; date: string | null; pages: number | null; chunks: number; status: 'indexing' | 'ready' | 'failed'; error: string | null; uploadId: string | null; seeded: boolean }
/** One event of an agent turn (backend agent.md, 7.2). */
export type AgentEvent =
  | { type: 'step'; payload: { label: string; status: 'running' | 'done' } }
  | { type: 'tool'; payload: { name: string; label: string; latencyMs: number } }
  | { type: 'flag'; payload: Flag }
  | { type: 'question'; payload: { text: string; options: { id: string; label: string; sub?: string | null }[] } }
  | { type: 'result'; payload: { runId: string; version: number } }
  | { type: 'change'; payload: { id: string; label: string; reason: string; patch: Partial<RunInput>; before: Record<string, unknown>; after: Record<string, unknown> } }
  | { type: 'citation'; payload: { index: number; label: string; source: string; passage: string } }
  | { type: 'text'; payload: { content: string } }
  | { type: 'error'; payload: { message: string; recoverable?: boolean } }
  | { type: 'done'; payload: { mode: 'llm' | 'script' } }

async function failure(res: Response) {
  const detail = await res.json().then((j) => j.detail, () => null)
  const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d) => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ') : res.statusText
  return new Error(msg || `Request failed (${res.status})`)
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

/** Send a message to the backend agent. The turn comes back as Server-Sent Events; `on` gets them one at a time, in order. */
async function agentTurn(simId: string, text: string, on: (e: AgentEvent) => void | Promise<void>) {
  const res = await send(`/simulations/${simId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
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

export const api = {
  products: () => req<Product[]>('GET', '/products'),
  createProduct: ({ id: _id, ...p }: Product) => req<Product>('POST', '/products', p),
  updateProduct: ({ id, ...p }: Product) => req<Product>('PUT', `/products/${encodeURIComponent(id)}`, p),
  snapshots: () => req<Snapshot[]>('GET', '/snapshots'),
  params: () => req<Parameters>('GET', '/parameters'),
  defaultParams: () => req<Parameters>('GET', '/parameters/defaults'),
  defaultInput: () => req<RunInput>('GET', '/parameters/default-run-input'),
  outlook: () => req<Outlook>('GET', '/outlook'),
  patchParams: (p: Partial<Parameters>) => req<Parameters>('PATCH', '/parameters', p),
  uploads: () => req<UploadFile[]>('GET', '/uploads'),
  detectUpload: (file: File) => { const f = new FormData(); f.append('file', file); return req<UploadDetection>('POST', '/uploads/detect', f) },
  addUpload: (u: UploadInput) => req<UploadFile>('POST', '/uploads', u),
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
  agentTurn,
  applyChange: (changeId: string, summary: string) => req<Run>('POST', `/changes/${changeId}/apply`, { summary }),
  dismissChange: (changeId: string) => req<void>('POST', `/changes/${changeId}/dismiss`),
  reset: () => req<void>('POST', '/reset'),
}

/** Show a failed request to the user. */
export function report(e: unknown) {
  toast.error(e instanceof Error ? e.message : 'Something went wrong')
}
