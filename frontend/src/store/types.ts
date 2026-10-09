import type { Flag, Method, RefId, Run, RunInput } from '@/engine/types'
import type { Period } from '@/engine/period'

export type Tab = 'costing' | 'pricing' | 'margin' | 'overview'
export type PinAxis = 'product' | 'strategy' | 'metric'

export interface QuestionOption { id: string; label: string; sub?: string; primary?: boolean }

export type Msg = { id: string } & (
  | { kind: 'user'; text: string }
  | { kind: 'text'; text: string; sources?: string[]; feedback?: boolean }
  | { kind: 'steps'; steps: { label: string; done: boolean }[]; collapsed?: boolean }
  | { kind: 'flag'; flag: Flag }
  | { kind: 'question'; text: string; flagId: string; options: QuestionOption[]; answered?: string; pending?: { input: RunInput } }
  | { kind: 'tool'; label: string }
  | { kind: 'result'; version: number }
  | { kind: 'change'; label: string; before: string; after: string; previews: { label: string; before: string; after: string }[]; patch: Partial<RunInput>; status: 'staged' | 'applied' | 'dismissed'; appliedVersion?: number; changeId?: string }
  | { kind: 'suggest'; items: string[] }
)

export interface SimView { tab: Tab; period: Period; ref: RefId; pin: PinAxis; version: number; product: string; strategy: Method | 'all'; metric: 'price' | 'cgm' | 'cgmP2O5' | 'total' }

export interface Simulation {
  id: string
  title: string
  createdAt: string
  runs: Run[]
  thread: Msg[]
  view: SimView
  busy?: boolean
}

export interface AppUI {
  theme: 'system' | 'light' | 'dark'
  sidebarOpen: boolean
  askOpen: boolean
  commandOpen: boolean
  runFormOpen: boolean
  memoOpen: boolean
  hypothesesOpen: boolean
  productSheetId: string | null
  uploadReviewOpen: boolean
  compareWith: number | null
}

type DOmit<T, K extends keyof never> = T extends unknown ? Omit<T, K> : never
export type NewMsg = DOmit<Msg, 'id'>
