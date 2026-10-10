import { Info } from 'lucide-react'
import { Card, Kpi } from '@/components/sim/atoms'
import { PivotTable } from '@/components/sim/PivotTable'
import type { SimData } from '@/components/sim/sim-context'
import { f2, millions, vsRef } from '@/lib/format'

export default function Margin({ data }: { data: SimData }) {
  const { result: r, input } = data
  const costPlus = r.methods.find((m) => m.method === 'costPlus')
  return (
    <div className="space-y-12">
      <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-4">
        <Kpi label="CGM per t product" value={f2(r.cgm)} unit="USD/t" delta={vsRef(r.deltaVsRef, input.referenceId, r.cgmRef)} />
        <Kpi label="CGM per t P2O5" value={f2(r.cgmP2O5)} unit="USD/t" delta={`${input.referenceId} ${f2(r.cgmRefP2O5)}`} />
        <Kpi label="CGM per t sulphur" value={f2(r.cgmS)} unit="USD/t" delta={`${f2(r.cgm)} ÷ ${(r.lines.find((l) => l.id === 'sulphur')?.qty ?? 0).toFixed(4)} t S/t`} />
        <Kpi label="Total margin" value={millions(r.totalMargin)} unit="M USD/yr" delta={`${(r.volume / 1000).toFixed(1)} kt · ${Math.round(input.marketShare * 1000) / 10}% share`} />
      </div>
      <Card title="Margin by method" sub={`CGM = price − unit cost (marketing, ${Math.round(input.marketingPct * 100)}% here, is part of the cost)`}>
        <PivotTable data={data} pin="product" />
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-muted p-3 text-[13px] text-muted-foreground">
          <Info className="size-3.5 shrink-0" />
          {r.prices.costPlus != null && r.anchorPrice != null ? `Every USD of price above the ${f2(r.floor)} floor goes straight to margin: the anchor earns ${f2(r.cgm)} USD/t, cost-plus ${f2(costPlus?.cgm)} USD/t.` : 'Add a reference price to compute margins.'}
        </div>
      </Card>
    </div>
  )
}
