import { useWidth } from '@/lib/hooks'
import { f2 } from '@/lib/format'
import type { ProductResult } from '@/engine/types'
import { cn } from '@/lib/utils'

export function PriceLadder({ r, refLabel, benchmark, mini, onAddBenchmark }: { r: ProductResult; refLabel: string; benchmark?: number | null; mini?: boolean; onAddBenchmark?: () => void }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const anchor = r.anchorPrice ?? r.floor
  const vals = [r.floor, anchor, r.ceiling, ...(r.refPrice != null ? [r.refPrice] : []), ...(benchmark != null ? [benchmark] : [])]
  const lo = Math.min(...vals) - 45
  const hi = Math.max(...vals) + 45
  const X = (v: number) => 12 + ((v - lo) / (hi - lo)) * Math.max(W - 24, 1)
  const H = mini ? 96 : benchmark == null ? 168 : 128
  const ty = mini ? 36 : 58
  const below = anchor < r.floor
  const lab = (x: number) => Math.max(46, Math.min(W - 46, x))
  const Label = ({ t, v, x, y, bold, muted, accent }: { t: string; v: string; x: number; y: number; bold?: boolean; muted?: boolean; accent?: boolean }) => (
    <div className="absolute flex -translate-x-1/2 flex-col items-center whitespace-nowrap" style={{ left: lab(x), top: y }}>
      <span className={cn(accent ? 'text-anchor' : 'text-muted-foreground', mini ? 'text-xs' : 'text-[13px]')}>{t}</span>
      <span className={cn('num', mini ? 'text-[13px]' : 'text-[13px]', bold ? 'font-semibold' : 'font-medium', accent ? 'text-anchor' : muted && 'text-muted-foreground')}>{v}</span>
    </div>
  )
  return (
    <div ref={ref} className="relative w-full" style={{ height: H }} data-testid="price-ladder">
      {W > 0 && (
        <>
          <div className="absolute h-[2px] rounded bg-border" style={{ left: 12, right: 12, top: ty + 6 }} />
          <div className="absolute h-3.5 rounded border border-primary/25 bg-accent" style={{ left: X(r.floor), width: Math.max(X(r.ceiling) - X(r.floor), 2), top: ty }} />
          {below && (
            <div
              className="absolute h-3.5 rounded-[3px] border border-warning-dot bg-warning-bg"
              style={{ left: X(anchor), width: X(r.floor) - X(anchor), top: ty, backgroundImage: 'repeating-linear-gradient(45deg, transparent 0 3px, color-mix(in oklab, var(--warning-dot) 45%, transparent) 3px 4px)' }}
              title="Below the cost-plus floor"
            />
          )}
          {r.refPrice != null && <div className="absolute w-0 border-l-[1.5px] border-dashed border-reference" style={{ left: X(r.refPrice), top: ty - 5, height: mini ? 24 : 30 }} />}
          {benchmark != null && <div className="absolute size-3 rotate-45 border-[1.5px] border-reference bg-background" style={{ left: X(benchmark) - 6, top: ty + 1 }} />}
          <div className="absolute size-4 rounded-full bg-anchor ring-2 ring-background" style={{ left: X(anchor) - 8, top: ty - 1 }} />
          <Label t="Cost-plus floor" v={f2(r.floor)} x={X(r.floor)} y={mini ? 0 : 6} />
          <Label t="Value ceiling" v={f2(r.ceiling)} x={X(r.ceiling)} y={mini ? 0 : 6} />
          {r.refPrice != null && <Label t={refLabel} v={String(Math.round(r.refPrice * 100) / 100)} x={X(r.refPrice)} y={ty + (mini ? 26 : 34)} muted />}
          <Label t="Recommended" v={f2(anchor)} x={X(anchor)} y={ty + (mini ? 22 : 26)} bold accent />
          {benchmark != null && <Label t="Market" v={f2(benchmark)} x={X(benchmark)} y={mini ? 0 : 6} />}
          {!mini && benchmark == null && (
            <button onClick={onAddBenchmark} className="absolute inline-flex h-8 items-center rounded-md border bg-background px-3 text-sm font-medium hover:bg-accent" style={{ right: 4, top: 132 }}>
              + Add market benchmark
            </button>
          )}
        </>
      )}
    </div>
  )
}
