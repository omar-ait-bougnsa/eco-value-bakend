// Test data only. The app loads its parameters and default run input from the backend.
import type { Parameters, RunInput } from '@/engine/types'
import { YTD } from '@/engine/period'

export const DEFAULT_PARAMS: Parameters = {
  costPlusMargin: 0.2,
  fullCost: false,
  valueShare: 1 / 3,
  marketingPct: 0,
  dnaPerTon: 96,
  marketShare: 0.05,
  rampTargetYear: 2030,
  priceType: 'low',
  carbonMarket: 'voluntary',
  freshnessMonths: 2,
  staleDays: 30,
  defaultReference: 'TSP',
}

export const ADDRESSABLE_MARKET_T = 14_630_675
export const TARGET_CROP_PRICE = 409 // USD/t (placeholder target crop)

export function defaultRunInput(p: Parameters, overrides: Partial<RunInput> = {}): RunInput {
  return {
    productIds: ['phos-65-35'],
    referenceId: p.defaultReference,
    periodFrom: YTD.from,
    periodTo: YTD.to,
    methods: ['costPlus', 'market', 'value', 'refMinus'],
    costPlusMargin: p.costPlusMargin,
    marketingPct: p.marketingPct,
    fullCost: p.fullCost,
    dnaPerTon: p.dnaPerTon,
    valueShare: p.valueShare,
    priceType: p.priceType,
    cropPrice: TARGET_CROP_PRICE,
    yieldGain: 0.12,
    appRateNew: 0.162,
    appRateRef: 0.13,
    pcfNew: 0.5,
    pcfRef: 0.7,
    carbonMarket: p.carbonMarket,
    carbonPrice: 0,
    marketShare: p.marketShare,
    rampTargetYear: p.rampTargetYear,
    addressable: ADDRESSABLE_MARKET_T,
    benchmark: null,
    anchor: 'refMinus',
    refCostOverride: null,
    comment: '',
    resolved: {},
    ...overrides,
  }
}
