import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, Pill, SourceChip, bannerAction } from '@/components/sim/atoms'
import { PriceLadder } from '@/components/sim/PriceLadder'
import type { SimData } from '@/components/sim/sim-context'
import { METHOD_LABEL, runProduct } from '@/engine/run'
import { dayShort, f2, pct } from '@/lib/format'
import { cn } from '@/lib/utils'
import { openHypotheses } from '@/components/sim/flag-actions'
import { isCurrentPeriod, periodLabel, periodWeights, yearPeriod } from '@/engine/period'
import { useApp } from '@/store/app'

export default function Pricing({ data }: { data: SimData }) {
  const { result: r, input, ctx, sim } = data
  const setView = useApp((s) => s.setView)
  const argus = ctx.uploads.find((u) => /argus/i.test(u.name)); const agro = ctx.uploads.find((u) => u.type === 'agro'); const crop = ctx.uploads.find((u) => u.type === 'crop')
  const prod = ctx.products.find((p) => p.id === r.productId)!
  const below = r.anchorPrice != null && r.anchorPrice < r.floor
  const addBench = () => openHypotheses('benchmark')
  const w = periodWeights({ from: input.periodFrom, to: input.periodTo })
  const years = ctx.snapshots.slice().reverse().map((s) => { const yp = yearPeriod(s.id === 'today' ? 2026 : +s.id); const x = runProduct({ ...data.run.input, periodFrom: yp.from, periodTo: yp.to, referenceId: input.referenceId }, ctx, r.productId); return { id: s.id, label: s.id === 'today' ? '2026 YTD' : s.id, x, active: (w[s.id] ?? 0) > 0 } })
  const MC = ({ m, badge, formula, srcs, anchor }: { m: 'costPlus' | 'refMinus' | 'value' | 'market'; badge: React.ReactNode; formula: string; srcs: string[]; anchor?: boolean }) => (
    <div className={cn('rounded-xl border bg-card p-6', anchor && 'border-anchor/50 ring-1 ring-anchor/15')} data-testid={`method-${m}`}>
      <div className="flex items-center justify-between"><h3 className="text-base font-semibold leading-6">{METHOD_LABEL[m]}</h3>{badge}</div>
      {r.prices[m] != null ? (
        <div className="mt-2 flex items-end gap-1.5"><span className="num text-[32px] font-medium leading-9 tracking-tight">{f2(r.prices[m])}</span><span className="pb-1 text-[13px] text-muted-foreground">USD/t</span></div>
      ) : <div className="mt-2 flex h-11 items-center text-lg font-medium text-subtle">Needs input</div>}
      <p className="mt-2 text-[13px] leading-[17px] text-muted-foreground">{formula}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{srcs.map((s) => <SourceChip key={s}>{s}</SourceChip>)}</div>
      {m === 'market' && r.prices.market == null && <Button size="sm" variant="outline" className="mt-3" onClick={addBench}>+ Add benchmark</Button>}
    </div>
  )
  return (
    <div className="space-y-12">
      <Card title="Price ladder" sub="Floor = cost-plus · anchor = reference minus · ceiling = value pricing">
        <PriceLadder r={r} refLabel={input.referenceId} benchmark={input.benchmark} onAddBenchmark={addBench} />
        {below && (
          <div className="mt-3 flex items-center gap-2.5 rounded-lg bg-warning-bg p-3 text-sm font-medium text-warning-fg">
            <AlertTriangle className="size-4 shrink-0" /> Anchor {f2(r.anchorPrice)} is below the cost-plus floor {f2(r.floor)} — at this price the margin over cost is thin.
            <button className={cn(bannerAction, 'ml-auto')} onClick={() => openHypotheses('anchor')}>Switch anchor</button>
          </div>
        )}
      </Card>
      <div className="grid gap-4 @2xl:grid-cols-2">
        <MC m="costPlus" badge={<Pill>Floor</Pill>} formula={`Unit cost ${f2(r.unitCost)} × (1 + ${pct(input.costPlusMargin, 0)} margin) = ${f2(r.prices.costPlus)}`} srcs={[isCurrentPeriod({ from: input.periodFrom, to: input.periodTo }) ? 'Standard cost · 2026' : `CRU averages · ${periodLabel({ from: input.periodFrom, to: input.periodTo })}`]} anchor={input.anchor === 'costPlus'} />
        <MC m="refMinus" badge={<Pill tone={input.anchor === 'refMinus' ? 'anchor' : 'default'}>{input.anchor === 'refMinus' ? 'Anchor' : 'Method'}</Pill>} formula={r.p2o5ValueRef != null ? `P2O5 in ${input.referenceId} is worth ${f2(r.p2o5ValueRef)} USD/t. ${r.name} holds ${pct(prod.composition.P2O5, 2)} P2O5 → ${f2(r.prices.refMinus)}.` : `No ${input.referenceId} price in this snapshot.`} srcs={[`Prices · ${argus ? dayShort(argus.fileDate) : '—'}`, 'Composition']} anchor={input.anchor === 'refMinus'} />
        <MC m="value" badge={<Pill>Ceiling</Pill>} formula={`${input.referenceId} ${f2(r.refPrice)} + ${pct(input.valueShare)} × ${f2(r.addedValue)} value created per t (${input.yieldGain} t/ha ÷ ${input.appRateNew} t/ha × ${input.cropPrice} USD/t)${r.carbonEffect ? ` + carbon ${f2(r.carbonEffect)}` : ''}.`} srcs={[`Agro trials · ${agro ? dayShort(agro.fileDate) : '—'}`, `Crop prices · ${crop ? dayShort(crop.fileDate) : '—'}`]} anchor={input.anchor === 'value'} />
        <MC m="market" badge={r.prices.market == null ? <Pill tone="warning">Optional</Pill> : <Pill>Benchmark</Pill>} formula={r.prices.market == null ? 'Enter a competitor price to compare it against the corridor.' : `Competitor benchmark entered by you: ${f2(r.prices.market)} USD/t.`} srcs={r.prices.market == null ? [] : ['You edited']} anchor={input.anchor === 'market'} />
      </div>
      <Card title="Across years" sub="Anchor price for each calendar year · the analysis period is highlighted · USD/t">
        <div className="overflow-x-auto">
          <table className="tbl w-full min-w-[640px] text-sm">
            <thead><tr className="border-b text-[13px] text-muted-foreground"><th className="py-2.5 text-left font-medium"> </th>{years.map((y) => <th key={y.id} className={cn('px-3 py-2.5 text-right font-medium', y.active && 'bg-muted')}>{y.label}</th>)}</tr></thead>
            <tbody>
              {([['Anchor price', (x: typeof years[0]['x']) => x.anchorPrice, true], [`${input.referenceId} reference price`, (x: typeof years[0]['x']) => x.refPrice, false], ['CGM at anchor', (x: typeof years[0]['x']) => x.cgm, false], [`${input.referenceId} CGM`, (x: typeof years[0]['x']) => x.cgmRef, false]] as const).map(([label, fn, bold]) => (
                <tr key={label} className="border-b"><td className={cn('py-3 pr-3', bold && 'font-medium')}>{label}</td>{years.map((y) => { const v = y.x.refPrice == null && label !== 'Anchor price' ? null : fn(y.x); return <td key={y.id} className={cn('num px-3 py-3 text-right', y.active && 'bg-muted font-medium', bold && 'font-medium')}>{v == null ? <span className="text-subtle">No data</span> : f2(v)}</td> })}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
