export type IngredientId = 'ammonia' | 'kcl' | 'rockDry' | 'rockWet' | 'sulphur' | 'acp'
export type Method = 'costPlus' | 'market' | 'value' | 'refMinus'
export type RefId = 'DAP' | 'MAP' | 'TSP'
export type PriceType = 'low' | 'high'
export type CarbonMarket = 'voluntary' | 'cbam'

export interface Composition { N: number; P2O5: number; K2O: number; S: number } // fractions

export interface Product {
  id: string
  name: string
  family: 'phosfusion' | 'reference' | 'other'
  recipe: Partial<Record<IngredientId, number>> // t ingredient / t product
  composition: Composition
  pcf: number | null // t CO2 / t product
  pcfPlaceholder?: boolean
  appRate: number | null // t product / ha
  yieldGain: number | null // t crop / ha vs reference
}

export interface Snapshot {
  id: string
  label: string
  asOf: string
  inputs: Record<IngredientId, number>
  refPrices: Record<RefId, { low: number | null; high: number | null }>
  source: string
}

export interface Parameters {
  costPlusMargin: number
  fullCost: boolean
  valueShare: number
  marketingPct: number
  dnaPerTon: number
  marketShare: number
  rampTargetYear: number
  priceType: PriceType
  carbonMarket: CarbonMarket
  freshnessMonths: number
  staleDays: number
  defaultReference: RefId
}

export type ResolvedKey = 'S1' | 'U1' | 'C2' | 'A1' | 'P1' | 'D1'

export interface RunInput {
  productIds: string[]
  referenceId: RefId
  periodFrom: string // Analysis period (ISO date, inclusive)
  periodTo: string
  methods: Method[]
  costPlusMargin: number
  marketingPct: number
  fullCost: boolean
  dnaPerTon: number
  valueShare: number
  priceType: PriceType
  cropPrice: number
  yieldGain: number
  appRateNew: number
  appRateRef: number
  pcfNew: number
  pcfRef: number
  carbonMarket: CarbonMarket
  carbonPrice: number
  marketShare: number
  rampTargetYear: number
  addressable: number
  benchmark: number | null
  anchor: Method
  refCostOverride: number | null
  comment: string
  resolved: Partial<Record<ResolvedKey, string | boolean>>
}

export type FlagSeverity = 'error' | 'warning' | 'info' | 'resolved'
export interface Flag {
  id: string
  code: string
  severity: FlagSeverity
  title: string
  detail?: string
  action?: { label: string; kind: 'answer' | 'open-input' | 'open-uploads' | 'open-product' | 'add-benchmark' | 'review' | 'dismiss'; target?: string }
}

export interface CostLine { id: IngredientId; label: string; qty: number; price: number; usd: number }
export interface MethodResult {
  method: Method
  label: string
  price: number | null
  cgm: number | null
  cgmP2O5: number | null
  totalMargin: number | null // USD / yr
  deltaVsRef: number | null
}

export interface ProductResult {
  productId: string
  name: string
  lines: CostLine[]
  rawMaterial: number
  dna: number
  marketing: number
  unitCost: number
  refPrice: number | null
  refCost: number | null
  p2o5ValueRef: number | null
  addedValue: number
  carbonSavingPerT: number
  carbonEffect: number
  prices: Record<Method, number | null>
  anchorPrice: number | null
  floor: number
  ceiling: number
  cgm: number | null
  cgmRef: number | null
  cgmP2O5: number | null
  cgmS: number | null
  volume: number
  totalMargin: number | null
  methods: MethodResult[]
  waterfall: { label: string; from: number; to: number; value: number; kind: 'total' | 'delta' }[]
  ramp: { year: number; kt: number }[]
  carbonScenarios: { id: string; label: string; price: number; delta: number }[]
}

export interface RunOutput {
  perProduct: Record<string, ProductResult>
  flags: Flag[]
}

export interface Run {
  id: string
  version: number
  input: RunInput
  output: RunOutput
  createdAt: string
  createdBy: 'user' | 'agent'
  summary: string
  changed: string[] // human-readable input changes vs previous run
  editedKeys: string[] // cumulative input keys changed vs v1
  productSig?: Record<string, string>
}

export interface UploadFile {
  id: string
  name: string
  type: 'prices' | 'freight' | 'agro' | 'crop'
  uploadedAt: string
  fileDate: string
  dataThrough: string
  detail?: string
}
