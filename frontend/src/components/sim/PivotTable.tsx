import { useMemo } from 'react'
import { METHOD_LABEL, runProduct } from '@/engine/run'
import type { Method, MethodResult } from '@/engine/types'
import { f2, millions, sign } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { SimData } from './sim-context'
import { Pill } from './atoms'

const METRIC_LABEL = { price: 'Price USD/t', cgm: 'CGM USD/t', cgmP2O5: 'CGM USD/t P2O5', total: 'Total margin M USD/yr' } as const
const pick = (m: MethodResult, metric: keyof typeof METRIC_LABEL) => (metric === 'price' ? m.price : metric === 'cgm' ? m.cgm : metric === 'cgmP2O5' ? m.cgmP2O5 : m.totalMargin)
const show = (v: number | null, metric: keyof typeof METRIC_LABEL) => (v == null ? '—' : metric === 'total' ? millions(v) : f2(v))

export function PivotTable({ data, pin: pinOverride }: { data: SimData; pin?: 'product' | 'strategy' | 'metric' }) {
  const { sim, input, ctx, result } = data
  const { metric, strategy } = sim.view
  const pin = pinOverride ?? sim.view.pin
  const all = useMemo(() => {
    const ids = Array.from(new Set([...input.productIds, ...ctx.products.filter((p) => p.family === 'phosfusion').map((p) => p.id)]))
    return ids.map((id) => runProduct(input, ctx, id))
  }, [input, ctx])
  const methods = (['costPlus', 'refMinus', 'value', 'market'] as Method[]).filter((m) => input.methods.includes(m))
  const th = 'whitespace-nowrap px-3 py-2.5 text-right text-[13px] font-medium text-muted-foreground'
  const td = 'whitespace-nowrap px-3 py-3 text-right num text-sm'

  if (pin === 'metric') {
    return (
      <div className="overflow-x-auto">
        <p className="mb-2 text-[13px] text-muted-foreground">Metric pinned: <b className="font-medium text-foreground">{METRIC_LABEL[metric]}</b> · products × strategies</p>
        <table className="tbl w-full min-w-[620px] text-sm">
          <thead><tr className="border-b"><th className={cn(th, 'text-left')}>Product</th>{methods.map((m) => <th key={m} className={th}>{METHOD_LABEL[m]}</th>)}</tr></thead>
          <tbody>{all.map((r) => (
            <tr key={r.productId} className={cn('border-b', r.productId === result.productId && 'bg-muted/60')}>
              <td className="px-3 py-3 text-sm">{r.name}</td>
              {methods.map((m) => { const mr = r.methods.find((x) => x.method === m); const v = mr ? pick(mr, metric) : null; return <td key={m} className={cn(td, m === input.anchor && 'font-semibold')}>{show(v, metric)}</td> })}
            </tr>
          ))}</tbody>
        </table>
      </div>
    )
  }
  const rows = pin === 'product'
    ? result.methods.map((m) => ({ key: m.method, label: `${result.name} · ${METHOD_LABEL[m.method]}`, anchor: m.method === input.anchor, price: m.price, cost: result.unitCost, cgm: m.cgm, p2: m.cgmP2O5, total: m.totalMargin, delta: m.deltaVsRef }))
    : all.map((r) => { const method = strategy === 'all' ? input.anchor : strategy; const m = r.methods.find((x) => x.method === method) ?? r.methods[0]; return { key: r.productId, label: `${r.name} · ${METHOD_LABEL[method]}`, anchor: r.productId === result.productId, price: m?.price ?? null, cost: r.unitCost, cgm: m?.cgm ?? null, p2: m?.cgmP2O5 ?? null, total: m?.totalMargin ?? null, delta: m?.deltaVsRef ?? null } })
  return (
    <div className="overflow-x-auto">
      <table className="tbl w-full min-w-[760px] text-sm">
        <thead><tr className="border-b"><th className={cn(th, 'text-left')}>{pin === 'product' ? 'Product · method' : 'Strategy pinned · products'}</th><th className={th}>Price</th><th className={th}>Unit cost</th><th className={th}>CGM / t</th><th className={th}>CGM / t P2O5</th><th className={th}>Total, M USD/yr</th><th className={th}>Δ vs {input.referenceId}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={cn('border-b', r.anchor && 'bg-muted/60')}>
              <td className="px-3 py-3 text-sm"><span className={cn(r.anchor && 'font-medium')}>{r.label}</span>{pin === 'product' && r.key === input.anchor && <Pill tone="anchor" className="ml-2">Anchor</Pill>}{pin === 'product' && r.key === 'costPlus' && <Pill className="ml-2">Floor</Pill>}{pin === 'product' && r.key === 'value' && <Pill className="ml-2">Ceiling</Pill>}</td>
              <td className={cn(td, r.price == null && 'text-subtle')}>{r.price == null ? 'Needs input' : f2(r.price)}</td>
              <td className={td}>{f2(r.cost)}</td>
              <td className={td}>{f2(r.cgm)}</td>
              <td className={td}>{r.p2 == null ? '—' : f2(r.p2)}</td>
              <td className={td}>{millions(r.total)}</td>
              <td className={td}>{r.delta == null ? '—' : sign(r.delta)}</td>
            </tr>
          ))}
          <tr><td className="px-3 py-3 text-sm text-muted-foreground">{input.referenceId} · reference (price {f2(result.refPrice)})</td><td className={td}>{f2(result.refPrice)}</td><td className={td}>{f2(result.refCost)}</td><td className={td}>{f2(result.cgmRef)}</td><td className={td}>{result.refPrice != null && result.cgmRef != null ? f2(result.cgmRef / (ctx.products.find((p) => p.id === input.referenceId)?.composition.P2O5 || 1)) : '—'}</td><td className={td}>—</td><td className={td}>—</td></tr>
        </tbody>
      </table>
    </div>
  )
}
export { METRIC_LABEL }
