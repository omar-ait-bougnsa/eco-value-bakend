// What the screens need to read a run. The numbers are calculated by the backend (POST /engine/run, /simulations/{id}/runs).
import type { Method, Parameters, Product, Snapshot, UploadFile } from './types'

/** The backend data a screen reads next to a run. */
export interface Ctx {
  products: Product[]
  snapshots: Snapshot[]
  uploads: UploadFile[]
  params: Parameters
}

export const METHOD_LABEL: Record<Method, string> = {
  costPlus: 'Cost-plus',
  market: 'Market pricing',
  value: 'Value pricing',
  refMinus: 'Reference minus',
}
