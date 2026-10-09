export const f2 = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace('-', '−'))
export const f1 = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).replace('-', '−'))
export const f0 = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? '—' : Math.round(n).toLocaleString('en-US').replace('-', '−'))
export const f3 = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 }))
export const pct = (n: number, d = 1) => `${(n * 100).toLocaleString('en-US', { maximumFractionDigits: d })}%`
export const millions = (n: number | null | undefined) => (n == null ? '—' : (n / 1e6).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).replace('-', '−'))
export const sign = (n: number, d = 2) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`
export const arrow = (n: number) => (n >= 0 ? '▲' : '▼')
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const parts = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return { y, m: MON[m - 1], d: String(d).padStart(2, '0') } }
export const dayLong = (iso: string) => { const p = parts(iso); return `${p.d} ${p.m} ${p.y}` }
export const dayShort = (iso: string) => { const p = parts(iso); return `${p.d} ${p.m}` }
export const timeShort = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, (globalThis as { __EVS_FAST__?: boolean }).__EVS_FAST__ ? 0 : ms))
