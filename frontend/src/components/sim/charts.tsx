import type { ReactNode } from 'react'
import { useWidth } from '@/lib/hooks'
import { f1, f2, sign } from '@/lib/format'
import type { CostLine, ProductResult } from '@/engine/types'
import { useApp } from '@/store/app'
import { Button } from '@/components/ui/button'
import { Info } from 'lucide-react'

function Sized({ h, children }: { h: number; children: (w: number) => ReactNode }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  return (
    <div ref={ref} className="w-full" style={{ height: h }}>
      {w > 0 && <svg width={w} height={h} className="block overflow-visible" role="img">{children(w)}</svg>}
    </div>
  )
}

const T = ({ x, y, children, anchor = 'start', mono, strong, size = 12, muted = true }: { x: number; y: number; children: ReactNode; anchor?: 'start' | 'middle' | 'end'; mono?: boolean; strong?: boolean; size?: number; muted?: boolean }) => (
  <text x={x} y={y} textAnchor={anchor} fontSize={size} className={`${muted ? 'fill-muted-foreground' : 'fill-foreground'} ${mono ? 'num' : ''}`} fontWeight={strong ? 600 : 400}>{children}</text>
)

export function MethodBars({ r, refLabel }: { r: ProductResult; refLabel: string }) {
  const rows: [string, number | null, string][] = [
    ['Cost-plus', r.prices.costPlus, 'fill-reference'],
    ['Reference minus', r.prices.refMinus, 'fill-anchor'],
    ['Value pricing', r.prices.value, 'fill-chart-1'],
    ['Market pricing', r.prices.market, 'fill-chart-3'],
  ]
  return (
    <Sized h={176}>
      {(w) => {
        const x0 = 112, mw = Math.max(w - x0 - 64, 40), max = Math.max(820, ...(rows.map((x) => x[1] ?? 0)), r.refPrice ?? 0) * 1.0
        const sc = (v: number) => (v / max) * mw
        return (
          <g>
            {rows.map(([label, v, cls], i) => {
              const y = 6 + i * 36
              return (
                <g key={label}>
                  <T x={0} y={y + 15} muted={false} size={13}>{label}</T>
                  {v != null ? (
                    <>
                      <rect x={x0} y={y} width={sc(v)} height={20} rx={3} className={cls} />
                      <T x={x0 + sc(v) + 8} y={y + 14} mono strong={i === 1} muted={false} size={12}>{f2(v)}</T>
                    </>
                  ) : (
                    <>
                      <rect x={x0} y={y} width={96} height={20} rx={3} fill="none" className="stroke-ring" strokeDasharray="3 3" />
                      <T x={x0 + 10} y={y + 14} size={12}>Needs input</T>
                    </>
                  )}
                </g>
              )
            })}
            {r.refPrice != null && (
              <g>
                <line x1={x0 + sc(r.refPrice)} x2={x0 + sc(r.refPrice)} y1={0} y2={142} className="stroke-ring" strokeDasharray="3 3" />
                <T x={x0 + sc(r.refPrice)} y={162} anchor="middle" mono>{refLabel} {f2(r.refPrice).replace('.00', '')}</T>
              </g>
            )}
          </g>
        )
      }}
    </Sized>
  )
}

export function RampChart({ ramp, share }: { ramp: ProductResult['ramp']; share: number }) {
  return (
    <Sized h={176}>
      {(w) => {
        const x0 = 40, x1 = w - 6, yb = 142, yt = 10
        const max = Math.max(...ramp.map((p) => p.kt), 100) * 1.1
        const Y = (v: number) => yb - ((yb - yt) * v) / max
        const X = (i: number) => x0 + ((x1 - x0) * i) / (ramp.length - 1)
        const line = ramp.map((p, i) => `${i ? 'L' : 'M'} ${X(i)} ${Y(p.kt)}`).join(' ')
        const area = `${line} L ${x1} ${yb} L ${x0} ${yb} Z`
        const peak = ramp.findIndex((p) => p.kt === Math.max(...ramp.map((q) => q.kt)))
        return (
          <g>
            {[0, 0.5, 1].map((t) => (
              <g key={t}>
                <line x1={x0} x2={x1} y1={yb - (yb - yt) * t} y2={yb - (yb - yt) * t} className="stroke-border" />
                <T x={x0 - 6} y={yb - (yb - yt) * t + 3} anchor="end" size={11}>{f1((max * t) / 1000)} Mt</T>
              </g>
            ))}
            <path d={area} className="fill-accent" />
            <path d={line} fill="none" className="stroke-primary" strokeWidth={1.75} strokeLinejoin="round" />
            <circle cx={X(peak)} cy={Y(ramp[peak].kt)} r={3.5} className="fill-primary" />
            <T x={X(peak) + 8} y={Y(ramp[peak].kt) - 8} mono muted={false} size={12}>{Math.round(share * 1000) / 10}% share · {f1(ramp[peak].kt)} kt</T>
            <T x={x0} y={yb + 18} size={11}>2026</T>
            <T x={X(peak)} y={yb + 18} anchor="middle" size={11}>{ramp[peak].year}</T>
            <T x={x1} y={yb + 18} anchor="end" size={11}>2035</T>
          </g>
        )
      }}
    </Sized>
  )
}

export function Waterfall({ r }: { r: ProductResult }) {
  const wf = r.waterfall
  return (
    <Sized h={176}>
      {(w) => {
        if (!wf.length) return <T x={0} y={20}>No reference price for this snapshot</T>
        const all = [0, ...wf.flatMap((b) => [b.from, b.to])]
        const mn = Math.min(...all), mx = Math.max(...all), yt = 24, yb = 136
        const Y = (v: number) => yt + ((mx - v) / (mx - mn || 1)) * (yb - yt)
        const bw = 52, gap = (w - bw * wf.length) / (wf.length + 1)
        return (
          <g>
            <defs>
              <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" strokeWidth="1.4" className="stroke-reference" /></pattern>
            </defs>
            <line x1={0} x2={w} y1={Y(0)} y2={Y(0)} className="stroke-ring" />
            {wf.map((b, i) => {
              const x = gap + (bw + gap) * i
              const top = Math.min(Y(b.from), Y(b.to)), h = Math.max(Math.abs(Y(b.from) - Y(b.to)), 2)
              const dec = b.kind === 'delta' && b.value < 0
              const cls = b.kind === 'total' ? 'fill-anchor' : dec ? '' : 'fill-chart-1'
              return (
                <g key={b.label}>
                  <rect x={x} y={top} width={bw} height={h} rx={2} className={cls} fill={dec ? 'url(#hatch)' : undefined} stroke={dec ? 'var(--reference)' : undefined} strokeDasharray={dec ? '3 2' : undefined} />
                  <T x={x + bw / 2} y={top - 6} anchor="middle" mono strong muted={false}>{b.kind === 'total' ? f2(b.value) : sign(b.value)}</T>
                  <foreignObject x={x + bw / 2 - (bw + gap - 6) / 2} y={yb + 6} width={bw + gap - 6} height={30}>
                    <div className="text-center text-xs leading-3 text-muted-foreground">{b.label}</div>
                  </foreignObject>
                </g>
              )
            })}
          </g>
        )
      }}
    </Sized>
  )
}

export function CarbonChart({ r, carbonPrice, onSet }: { r: ProductResult; carbonPrice: number; onSet: () => void }) {
  if (carbonPrice === 0) {
    return (
      <div className="relative flex h-[176px] items-center justify-center">
        <div className="absolute inset-x-8 bottom-6 flex items-end justify-center gap-4 opacity-70">
          {[28, 49, 66, 84].map((h, i) => <div key={i} className="w-12 rounded border border-dashed" style={{ height: h }} />)}
        </div>
        <div className="relative flex flex-col items-center gap-1.5 rounded-[10px] border bg-card p-3.5 text-center">
          <Info className="size-4 text-muted-foreground" />
          <div className="text-sm font-medium">Add a carbon price</div>
          <div className="text-[13px] text-muted-foreground">Carbon effect is 0 until a price is set</div>
          <Button size="sm" variant="outline" className="mt-1" onClick={onSet}>Set carbon price</Button>
        </div>
      </div>
    )
  }
  const sc = r.carbonScenarios
  return (
    <Sized h={176}>
      {(w) => {
        const max = Math.max(...sc.map((s) => s.delta), 0.01)
        const bw = 56, gap = (w - bw * sc.length) / (sc.length + 1)
        return (
          <g>
            <line x1={0} x2={w} y1={140} y2={140} className="stroke-ring" />
            {sc.map((s, i) => {
              const h = (s.delta / max) * 96
              const x = gap + (bw + gap) * i
              return (
                <g key={s.id}>
                  <rect x={x} y={140 - h} width={bw} height={h} rx={3} className={s.price === carbonPrice ? 'fill-anchor' : 'fill-reference'} />
                  <T x={x + bw / 2} y={140 - h - 6} anchor="middle" mono strong muted={false}>+{f2(s.delta)}</T>
                  <T x={x + bw / 2} y={156} anchor="middle" size={11}>{s.label}</T>
                  <T x={x + bw / 2} y={168} anchor="middle" size={11} mono>{s.price} USD/t</T>
                </g>
              )
            })}
          </g>
        )
      }}
    </Sized>
  )
}

const ING_FILL: Record<string, string> = { sulphur: 'fill-anchor', rockDry: 'fill-chart-2', rockWet: 'fill-chart-3', ammonia: 'fill-chart-1', kcl: 'fill-reference', acp: 'fill-border' }
export function CostStack({ rows }: { rows: { label: string; lines: CostLine[]; extra?: { label: string; usd: number }[] }[] }) {
  const maxTotal = Math.max(...rows.map((r) => r.lines.reduce((a, l) => a + l.usd, 0) + (r.extra?.reduce((a, e) => a + e.usd, 0) ?? 0)), 1)
  return (
    <Sized h={20 + rows.length * 54}>
      {(w) => {
        const x0 = 150, mw = Math.max(w - x0 - 76, 50), sc = (v: number) => (v / (maxTotal * 1.02)) * mw
        return (
          <g>
            {rows.map((r, ri) => {
              const y = 10 + ri * 54
              let x = x0
              const total = r.lines.reduce((a, l) => a + l.usd, 0) + (r.extra?.reduce((a, e) => a + e.usd, 0) ?? 0)
              return (
                <g key={r.label}>
                  <T x={0} y={y + 20} muted={false} size={13} strong>{r.label}</T>
                  {[...r.lines.map((l) => ({ id: l.id, label: l.label, usd: l.usd })), ...(r.extra ?? []).map((e) => ({ id: 'acp', label: e.label, usd: e.usd }))].map((l) => {
                    const wd = sc(l.usd); const xx = x; x += wd + 1
                    return (
                      <g key={l.label}>
                        <rect x={xx} y={y} width={wd} height={30} className={ING_FILL[l.id] ?? 'fill-border'} />
                        {wd > 54 && <T x={xx + wd / 2} y={y + 19} anchor="middle" mono size={12} muted={false}><tspan className={l.id === 'sulphur' || l.id === 'rockDry' || l.id === 'ammonia' ? 'fill-white' : 'fill-foreground'}>{f2(l.usd)}</tspan></T>}
                      </g>
                    )
                  })}
                  <T x={x + 8} y={y + 20} mono strong muted={false} size={13}>{f2(total)}</T>
                </g>
              )
            })}
          </g>
        )
      }}
    </Sized>
  )
}

export function Legend({ items }: { items: { label: string; cls: string }[] }) {
  return (
    <div className="flex flex-wrap gap-3.5">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><span className={`size-2.5 rounded-sm ${i.cls}`} />{i.label}</span>
      ))}
    </div>
  )
}
export const ING_LEGEND = [
  { label: 'Rock (dry)', cls: 'bg-chart-2' }, { label: 'Rock (wet)', cls: 'bg-chart-3' }, { label: 'Sulphur', cls: 'bg-anchor' }, { label: 'Ammonia', cls: 'bg-chart-1' }, { label: 'KCl', cls: 'bg-reference' },
]

export function TrendLines() {
  const OUTLOOK = useApp((s) => s.outlook)
  const series: [string, number[], string, string | undefined][] = [
    ['Sulphur', OUTLOOK.sulphur, 'stroke-anchor', undefined],
    ['Ammonia', OUTLOOK.ammonia, 'stroke-chart-1', undefined],
    ['KCl', OUTLOOK.kcl, 'stroke-reference', '4 3'],
  ]
  return (
    <Sized h={230}>
      {(w) => {
        const xs = 42, xe = w - 78, yb = 200, yt = 14, mx = 950
        const X = (i: number) => xs + ((xe - xs) * i) / 8, Y = (v: number) => yb - ((yb - yt) * v) / mx
        const ends = series.map(([, v]) => Y(v[8])).sort((a, b) => a - b)
        return (
          <g>
            {[0, 1, 2, 3].map((i) => (<g key={i}><line x1={xs} x2={xe + 30} y1={yb - ((yb - yt) * i) / 3} y2={yb - ((yb - yt) * i) / 3} className="stroke-border" /><T x={xs - 6} y={yb - ((yb - yt) * i) / 3 + 3} anchor="end" size={11}>{Math.round((mx * i) / 3 / 50) * 50}</T></g>))}
            {series.map(([n, v, cls, dash]) => (
              <g key={n}>
                <path d={v.map((val, i) => `${i ? 'L' : 'M'} ${X(i)} ${Y(val)}`).join(' ')} fill="none" className={cls} strokeWidth={1.75} strokeDasharray={dash} strokeLinejoin="round" />
              </g>
            ))}
            {series.map(([n, v]) => {
              const idx = ends.indexOf(Y(v[8]))
              return <T key={n} x={X(8) + 8} y={ends[0] + idx * 15 + 4} mono muted={false} size={12}>{n} {v[8]}</T>
            })}
            {[0, 2, 4, 6, 8].map((i) => <T key={i} x={X(i)} y={yb + 18} anchor="middle" size={11}>{OUTLOOK.years[i]}</T>)}
          </g>
        )
      }}
    </Sized>
  )
}
