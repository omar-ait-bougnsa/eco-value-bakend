import { describe, expect, it } from 'vitest'
import { runEngine } from './run'
import { PRODUCTS } from '@/test-fixtures/products'
import { SNAPSHOTS } from '@/test-fixtures/snapshots'
import { SEED_UPLOADS } from '@/test-fixtures/uploads'
import { DEFAULT_PARAMS, defaultRunInput } from '@/test-fixtures/defaults'
import { blendSnapshot, dayPeriod, monthPeriod, last12Months, periodLabel, periodWeights, yearPeriod, YTD } from './period'

const ctx = { products: PRODUCTS, snapshots: SNAPSHOTS, uploads: SEED_UPLOADS, params: DEFAULT_PARAMS }
const near = (a: number | null | undefined, b: number, d = 2) => expect(a).toBeCloseTo(b, d)

describe('engine · Today · Phosfusion 65-35 vs TSP', () => {
  const out = runEngine(defaultRunInput(DEFAULT_PARAMS), ctx)
  const r = out.perProduct['phos-65-35']
  it('costs', () => {
    near(r.unitCost, 310.9)
    near(r.prices.costPlus, 373.08)
    near(r.refCost, 655.18)
    near(r.refPrice, 640, 6)
  })
  it('prices', () => {
    near(r.prices.refMinus, 313.91)
    near(r.prices.value, 740.99)
    near(r.addedValue, 302.96)
    near(r.p2o5ValueRef, 1391.3, 1)
    expect(r.prices.market).toBeNull()
  })
  it('margins', () => {
    near(r.cgm, 3.02)
    near(r.cgmRef, -15.18)
    near(r.cgmP2O5, 13.37)
    near(r.cgmS, 18.86)
    near((r.totalMargin ?? 0) / 1e6, 2.2, 1)
  })
  it('waterfall closes', () => {
    const w = r.waterfall
    near(w[0].to + w[1].value + w[2].value, w[3].to)
  })
  it('flags include P1, D1, S1, U1, C2, M1, A1', () => {
    const codes = out.flags.map((f) => f.code)
    for (const c of ['P1', 'D1', 'S1', 'U1', 'C2', 'M1', 'A1']) expect(codes).toContain(c)
  })
})

describe('what-ifs and other snapshots', () => {
  it('value share 50% → 791.48', () => {
    const r = runEngine(defaultRunInput(DEFAULT_PARAMS, { valueShare: 0.5 }), ctx).perProduct['phos-65-35']
    near(r.prices.value, 791.48)
  })
  it('deck TSP cost 494 → reference CGM 146', () => {
    const r = runEngine(defaultRunInput(DEFAULT_PARAMS, { refCostOverride: 494 }), ctx).perProduct['phos-65-35']
    near(r.cgmRef, 146)
  })
  it('2025 snapshot', () => {
    const r = runEngine(defaultRunInput(DEFAULT_PARAMS, { periodFrom: '2025-01-01', periodTo: '2025-12-31' }), ctx).perProduct['phos-65-35']
    near(r.unitCost, 214.81)
    near(r.prices.refMinus, 259.62)
    near(r.cgmRef, 182.3, 1)
  })
  it('anchor trend 2021-2025', () => {
    const exp: Record<string, number> = { '2021': 269.38, '2022': 402.64, '2023': 220.43, '2024': 213.9 }
    for (const [id, v] of Object.entries(exp)) near(runEngine(defaultRunInput(DEFAULT_PARAMS, { periodFrom: `${id}-01-01`, periodTo: `${id}-12-31` }), ctx).perProduct['phos-65-35'].prices.refMinus, v)
  })
  it('DAP reference', () => {
    const r = runEngine(defaultRunInput(DEFAULT_PARAMS, { referenceId: 'DAP' }), ctx).perProduct['phos-65-35']
    near(r.prices.refMinus, 352.67, 1)
    near(r.prices.value, 920.99)
  })
  it('phosfusion 50-50', () => {
    const r = runEngine(defaultRunInput(DEFAULT_PARAMS, { productIds: ['phos-50-50'] }), ctx).perProduct['phos-50-50']
    near(r.unitCost, 270.33)
    near(r.prices.refMinus, 265.4)
  })
})

describe('analysis period', () => {
  it('year to date is exactly the current snapshot (golden numbers unchanged)', () => {
    expect(periodWeights(YTD).today).toBeCloseTo(1, 6)
    expect(blendSnapshot(SNAPSHOTS, YTD).id).toBe('today')
    expect(periodLabel(YTD)).toBe('Year to date')
  })
  it('a calendar year maps to that year only, and labels read naturally', () => {
    expect(periodWeights(yearPeriod(2024))).toEqual({ '2024': 1 })
    expect(periodLabel(yearPeriod(2023))).toBe('2023')
    expect(periodLabel({ from: '2025-03-01', to: '2025-06-30' })).toBe('01 Mar 2025 – 30 Jun 2025')
  })
  it('a period spanning two years is the day-weighted blend', () => {
    const p = { from: '2024-07-01', to: '2025-06-30' } // 184 days of 2024 + 181 of 2025
    const w = periodWeights(p)
    expect(w['2024'] + w['2025']).toBeCloseTo(1, 6)
    const b = blendSnapshot(SNAPSHOTS, p)
    const s24 = SNAPSHOTS.find((s) => s.id === '2024')!, s25 = SNAPSHOTS.find((s) => s.id === '2025')!
    near(b.inputs.sulphur, w['2024'] * s24.inputs.sulphur + w['2025'] * s25.inputs.sulphur, 6)
  })
  it('last 12 months blends 2025 and the current year; S1 only asks when the period is entirely current', () => {
    const l12 = last12Months()
    const w = periodWeights(l12)
    expect(w['2025']).toBeGreaterThan(0.2); expect(w.today).toBeGreaterThan(0.6)
    const out = runEngine(defaultRunInput(DEFAULT_PARAMS, { periodFrom: l12.from, periodTo: l12.to }), ctx)
    expect(out.flags.some((f) => f.code === 'S1')).toBe(false)
    expect(runEngine(defaultRunInput(DEFAULT_PARAMS), ctx).flags.some((f) => f.code === 'S1' && f.severity === 'warning')).toBe(true)
  })
})

describe('day / month / year selection', () => {
  it('a day, a month and a year all resolve and label naturally', () => {
    expect(periodLabel(dayPeriod('2025-03-14'))).toBe('14 Mar 2025')
    expect(monthPeriod('2025-02')).toEqual({ from: '2025-02-01', to: '2025-02-28' })
    expect(periodLabel(monthPeriod('2025-02'))).toBe('Feb 2025')
    expect(monthPeriod('2026-10').to).toBe('2026-10-02') // current month is cut at today
    expect(periodLabel(monthPeriod('2026-10'))).toBe('Oct 2026')
  })
  it('a single day uses its year, a month inside one year too', () => {
    expect(periodWeights(dayPeriod('2024-05-01'))).toEqual({ '2024': 1 })
    expect(periodWeights(monthPeriod('2023-11'))).toEqual({ '2023': 1 })
    const out = runEngine(defaultRunInput(DEFAULT_PARAMS, { periodFrom: '2024-05-01', periodTo: '2024-05-01' }), ctx).perProduct['phos-65-35']
    near(out.unitCost, 183.4)
  })
})
