import { useNavigate } from 'react-router-dom'
import { Card, FlagRow, Kpi } from '@/components/sim/atoms'
import { CarbonChart, MethodBars, RampChart, Waterfall } from '@/components/sim/charts'
import { PriceLadder } from '@/components/sim/PriceLadder'
import { PivotBar } from '@/components/sim/PivotBar'
import { PivotTable } from '@/components/sim/PivotTable'
import { openFlagTarget, openHypotheses } from '@/components/sim/flag-actions'
import type { SimData } from '@/components/sim/sim-context'
import { diffInputs } from '@/engine/run'
import { METHOD_LABEL } from '@/engine/run'
import { arrow, f2, millions, pct, sign } from '@/lib/format'
import { useApp } from '@/store/app'
import { cn } from '@/lib/utils'

const KEYLABEL: Record<string, string> = { valueShare: 'Value share', costPlusMargin: 'Cost-plus margin', carbonPrice: 'Carbon price', marketShare: 'Market share', benchmark: 'Market benchmark', fullCost: 'Include D&A', anchor: 'Anchor method', yieldGain: 'Yield gain', cropPrice: 'Crop price', refCostOverride: 'TSP cost override', periodFrom: 'Period start', periodTo: 'Period end', referenceId: 'Reference', priceType: 'Price type', appRateNew: 'Application rate', pcfNew: 'Carbon footprint', marketingPct: 'Marketing %', methods: 'Methods', productIds: 'Products' }
const fmtVal = (k: string, v: unknown) => (v == null ? '—' : ['valueShare', 'costPlusMargin', 'marketShare', 'marketingPct'].includes(k) ? pct(v as number) : typeof v === 'number' ? String(Math.round((v as number) * 1000) / 1000) : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v))

export function ComparePanel({ data }: { data: SimData }) {
  const cmp = data.compare!; const { run } = data
  const diffs = diffInputs(cmp.input, run.input)
  const a = cmp.output.perProduct[run.input.productIds[0]]; const b = run.output.perProduct[run.input.productIds[0]]
  const rows = (['costPlus', 'refMinus', 'value', 'market'] as const).map((m) => ({ m, a: a.prices[m], b: b.prices[m] }))
  return (
    <div className="grid gap-4 @3xl:grid-cols-2" data-testid="compare-panel">
      <Card title="Changed inputs" sub={`v${cmp.version} → v${run.version}`}>
        {diffs.length === 0 ? <p className="text-sm text-muted-foreground">No input changed.</p> : (
          <div className="space-y-2">{diffs.map((d) => (
            <div key={String(d.key)} className="flex items-center gap-2 rounded-lg border p-3 text-sm">
              <span>{KEYLABEL[String(d.key)] ?? String(d.key)}</span><span className="flex-1" />
              <span className="num text-muted-foreground line-through">{fmtVal(String(d.key), d.before)}</span><span className="text-muted-foreground">→</span><span className="num font-semibold">{fmtVal(String(d.key), d.after)}</span>
            </div>))}</div>
        )}
        <div className="mt-3 text-[13px] text-muted-foreground">Reason</div>
        <p className="text-sm">{run.input.comment || run.summary}</p>
      </Card>
      <Card title="Output changes" sub="USD/t">
        <table className="tbl w-full text-sm"><thead><tr className="border-b text-[13px] text-muted-foreground"><th className="py-2 text-left font-medium">Method</th><th className="py-2 text-right font-medium">v{cmp.version}</th><th className="py-2 text-right font-medium">v{run.version}</th><th className="py-2 text-right font-medium">Δ</th></tr></thead>
          <tbody>{rows.map(({ m, a: x, b: y }) => { const ch = x != null && y != null && Math.abs(x - y) > 0.004; return (
            <tr key={m} className={cn('border-b', ch && 'bg-muted/60')}><td className="py-2.5">{METHOD_LABEL[m]}</td><td className="num py-2.5 text-right">{x == null ? 'Needs input' : f2(x)}</td><td className="num py-2.5 text-right">{y == null ? 'Needs input' : f2(y)}</td><td className="num py-2.5 text-right font-medium">{ch ? sign(y! - x!) : '—'}</td></tr>) })}</tbody></table>
      </Card>
    </div>
  )
}

export default function Overview({ data }: { data: SimData }) {
  const nav = useNavigate(); const setView = useApp((s) => s.setView)
  const { result: r, input, out, sim, compare } = data
  const cmpR = compare?.output.perProduct[r.productId]
  const dlt = (now: number | null, was: number | null | undefined) => (cmpR && now != null && was != null && Math.abs(now - was) > 0.004 ? `${arrow(now - was)} ${sign(now - was)} vs v${compare!.version}` : cmpR ? `no change vs v${compare!.version}` : null)
  const refP2 = data.ctx.products.find((p) => p.id === input.referenceId)?.composition.P2O5 ?? 1
  const open = out.flags.filter((f) => f.severity !== 'resolved')
  const gotoHyp = (k: string) => openHypotheses(k)
  return (
    <div className="space-y-12">
      <PivotBar data={data} />
      <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-4">
        <Kpi label="Recommended price" value={f2(r.anchorPrice)} unit="USD/t" delta={dlt(r.anchorPrice, cmpR?.anchorPrice) ?? METHOD_LABEL[input.anchor]} />
        <Kpi label="CGM per t" value={f2(r.cgm)} unit="USD/t" delta={dlt(r.cgm, cmpR?.cgm) ?? `${arrow((r.cgm ?? 0) - (r.cgmRef ?? 0))} ${f2(Math.abs((r.cgm ?? 0) - (r.cgmRef ?? 0)))} vs ${input.referenceId} ${f2(r.cgmRef)}`} />
        <Kpi label="CGM per t P2O5" value={f2(r.cgmP2O5)} unit="USD/t" delta={`${input.referenceId} ${r.cgmRef != null ? f2(r.cgmRef / refP2) : '—'}`} />
        <Kpi label="Total margin" value={millions(r.totalMargin)} unit="M USD/yr" delta={`${Math.round(input.marketShare * 1000) / 10}% share · ${f2(r.volume / 1000).replace('.00', '')} kt`} />
      </div>
      <Card title="Price ladder" sub="Floor = cost-plus · anchor = reference minus · ceiling = value pricing">
        <PriceLadder r={r} refLabel={input.referenceId} benchmark={input.benchmark} onAddBenchmark={() => gotoHyp('benchmark')} />
      </Card>
      <Card title="Pivot view" sub={{ product: 'Product pinned — methods compared', strategy: 'Strategy pinned — all products on one strategy', metric: 'Metric pinned — products × strategies' }[sim.view.pin]}><PivotTable data={data} /></Card>
      <Card title="Flags to resolve" sub={`${open.length} open · ${out.flags.length - open.length} resolved`}>
        <div className="space-y-1.5">
          {out.flags.map((f) => <FlagRow key={f.id} flag={f} onAction={(fl) => (fl.action?.kind === 'review' ? setView(sim.id, { tab: 'pricing' }) : openFlagTarget(fl, sim.id, nav))} />)}
        </div>
      </Card>
      <div className="grid gap-4 @3xl:grid-cols-2">
        <Card title="Price by method" sub={`USD/t · vertical line = ${input.referenceId}`}><MethodBars r={r} refLabel={input.referenceId} /></Card>
        <Card title="Volume ramp-up" sub="Illustrative, not a forecast · kt/yr"><RampChart ramp={r.ramp} share={input.marketShare} /></Card>
        <Card title="CGM waterfall" sub={`USD/t · ${input.referenceId} → new product`}><Waterfall r={r} /></Card>
        <Card title="Carbon scenarios" sub="USD/t · voluntary vs CBAM"><CarbonChart r={r} carbonPrice={input.carbonPrice} onSet={() => gotoHyp('carbonPrice')} /></Card>
      </div>
    </div>
  )
}
