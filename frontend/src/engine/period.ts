// Analysis periods as the UI handles them: picking, clamping and naming dates.
// The dates themselves come from the backend (GET /periods/range, /periods/presets); blending market data over a period is its job.

export interface Period { from: string; to: string } // ISO dates, inclusive
export interface PeriodPreset { id: string; label: string; period: Period }

let range: Period = { from: '', to: '' }
let presets: PeriodPreset[] = []

/** Called once the backend has answered, before anything renders. */
export function setPeriodData(r: Period, p: PeriodPreset[]) { range = r; presets = p }

/** The days the market data covers. The last one is "today" for the simulator. */
export const dataRange = () => range
export const periodPresets = () => presets
export const currentYear = () => Number(range.to.slice(0, 4))
/** Calendar years with data, newest first. */
export const dataYears = () => { const out: number[] = []; for (let y = currentYear(); y >= Number(range.from.slice(0, 4)); y--) out.push(y); return out }
export const ytd = (): Period => ({ from: `${currentYear()}-01-01`, to: range.to })

export function clampPeriod(p: Period): Period {
  let from = p.from < range.from ? range.from : p.from > range.to ? range.to : p.from
  let to = p.to > range.to ? range.to : p.to < range.from ? range.from : p.to
  if (from > to) [from, to] = [to, from]
  return { from, to }
}

/** The current year stops at today. */
export function yearPeriod(y: number): Period {
  return y >= currentYear() ? ytd() : { from: `${y}-01-01`, to: `${y}-12-31` }
}

export const dayPeriod = (d: string): Period => clampPeriod({ from: d, to: d })

/** `ym` is "YYYY-MM". The current month is cut at today. */
export function monthPeriod(ym: string): Period {
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return clampPeriod({ from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, '0')}` })
}

export const samePeriod = (a: Period, b: Period) => a.from === b.from && a.to === b.to
export const overlaps = (a: Period, b: Period) => a.from <= b.to && b.from <= a.to
/** A period entirely inside the current year: it is priced with today's market data, not a blend of past years. */
export const isCurrentPeriod = (p: Period) => clampPeriod(p).from >= ytd().from

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const fmt = (s: string) => { const [y, m, d] = s.split('-').map(Number); return `${String(d).padStart(2, '0')} ${MON[m - 1]} ${y}` }

/** The backend's name for the period when it is one of its presets, else the dates. */
export function periodLabel(p0: Period): string {
  const p = clampPeriod(p0)
  const preset = presets.find((x) => samePeriod(x.period, p))
  if (preset) return preset.label
  if (p.from === p.to) return fmt(p.from)
  const mp = monthPeriod(p.from.slice(0, 7))
  if (samePeriod(p, mp)) { const [y, m] = p.from.split('-').map(Number); return `${MON[m - 1]} ${y}` }
  return `${fmt(p.from)} – ${fmt(p.to)}`
}
