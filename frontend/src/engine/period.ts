import type { Snapshot } from './types'

export interface Period { from: string; to: string } // ISO dates, inclusive

export const DATA_START = '2021-01-01'
export const DATA_END = '2026-10-02' // "today" in the demo; the 2026 snapshot covers 1 Jan → today
export const YTD: Period = { from: '2026-01-01', to: DATA_END }

const day = (iso: string) => Math.floor(new Date(iso + 'T00:00:00Z').getTime() / 864e5)
const iso = (d: number) => new Date(d * 864e5).toISOString().slice(0, 10)

export function clampPeriod(p: Period): Period {
  let from = p.from < DATA_START ? DATA_START : p.from > DATA_END ? DATA_END : p.from
  let to = p.to > DATA_END ? DATA_END : p.to < DATA_START ? DATA_START : p.to
  if (from > to) [from, to] = [to, from]
  return { from, to }
}

export function yearPeriod(y: number): Period {
  return y >= 2026 ? YTD : { from: `${y}-01-01`, to: `${y}-12-31` }
}

export const dayPeriod = (d: string): Period => clampPeriod({ from: d, to: d })

/** `ym` is "YYYY-MM". The current month is cut at today. */
export function monthPeriod(ym: string): Period {
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return clampPeriod({ from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, '0')}` })
}

export function last12Months(): Period {
  return { from: iso(day(DATA_END) - 364), to: DATA_END }
}

export const PERIOD_PRESETS: { id: string; label: string; period: Period }[] = [
  { id: 'ytd', label: 'Year to date', period: YTD },
  { id: 'l12', label: 'Last 12 months', period: last12Months() },
  ...[2025, 2024, 2023, 2022, 2021].map((y) => ({ id: String(y), label: String(y), period: yearPeriod(y) })),
  { id: '2021-25', label: '2021–2025', period: { from: '2021-01-01', to: '2025-12-31' } },
]

/** Share of the period (by days) that falls in each yearly snapshot. 2026 maps to the "today" snapshot. */
export function periodWeights(p0: Period): Record<string, number> {
  const p = clampPeriod(p0)
  const total = day(p.to) - day(p.from) + 1
  const out: Record<string, number> = {}
  for (let y = 2021; y <= 2026; y++) {
    const ys = y === 2026 ? '2026-01-01' : `${y}-01-01`
    const ye = y === 2026 ? DATA_END : `${y}-12-31`
    const a = Math.max(day(p.from), day(ys)), b = Math.min(day(p.to), day(ye))
    const n = b - a + 1
    if (n > 0) out[y === 2026 ? 'today' : String(y)] = n / total
  }
  return out
}

export const isCurrentPeriod = (p: Period) => (periodWeights(p).today ?? 0) > 0.9999
export const touchesCurrentYear = (p: Period) => (periodWeights(p).today ?? 0) > 0

/** Day-weighted blend of the yearly snapshots covering the period. A period inside 2026 returns the "today" snapshot untouched. */
export function blendSnapshot(snapshots: Snapshot[], p0: Period): Snapshot {
  const p = clampPeriod(p0)
  const w = periodWeights(p)
  const byId = Object.fromEntries(snapshots.map((s) => [s.id, s]))
  if ((w.today ?? 0) > 0.9999) return byId.today
  const ids = Object.keys(w).filter((id) => byId[id])
  const sum = ids.reduce((a, id) => a + w[id], 0)
  const mix = (f: (s: Snapshot) => number | null): number | null => {
    let acc = 0
    for (const id of ids) { const v = f(byId[id]); if (v == null) return null; acc += (w[id] / sum) * v }
    return acc
  }
  const keys = Object.keys(byId.today.inputs) as (keyof Snapshot['inputs'])[]
  const inputs = Object.fromEntries(keys.map((k) => [k, mix((s) => s.inputs[k]) ?? 0])) as Snapshot['inputs']
  const ref = (r: 'DAP' | 'MAP' | 'TSP') => ({ low: mix((s) => s.refPrices[r].low), high: null as number | null })
  return {
    id: 'period', label: periodLabel(p), asOf: p.to, inputs,
    refPrices: { DAP: ref('DAP'), MAP: ref('MAP'), TSP: ref('TSP') },
    source: 'Day-weighted blend of yearly averages (CRU) and current Standard cost / Argus inputs',
  }
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const fmt = (s: string) => { const [y, m, d] = s.split('-').map(Number); return `${String(d).padStart(2, '0')} ${MON[m - 1]} ${y}` }

export function periodLabel(p0: Period): string {
  const p = clampPeriod(p0)
  if (p.from === YTD.from && p.to === YTD.to) return 'Year to date'
  const l12 = last12Months()
  if (p.from === l12.from && p.to === l12.to) return 'Last 12 months'
  if (p.from === '2021-01-01' && p.to === '2025-12-31') return '2021–2025'
  for (let y = 2021; y <= 2025; y++) if (p.from === `${y}-01-01` && p.to === `${y}-12-31`) return String(y)
  if (p.from === p.to) return fmt(p.from)
  const mp = monthPeriod(p.from.slice(0, 7))
  if (p.from.slice(0, 7) === p.to.slice(0, 7) && p.from === mp.from && p.to === mp.to) {
    const [y, m] = p.from.split('-').map(Number)
    return `${MON[m - 1]} ${y}`
  }
  return `${fmt(p.from)} – ${fmt(p.to)}`
}

export const samePeriod = (a: Period, b: Period) => a.from === b.from && a.to === b.to
