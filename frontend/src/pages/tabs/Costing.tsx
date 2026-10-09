import { Card, Kpi, SourceChip } from '@/components/sim/atoms'
import { CostStack, ING_LEGEND, Legend, TrendLines } from '@/components/sim/charts'
import type { SimData } from '@/components/sim/sim-context'
import { costLines, getProduct, resolveSnapshot } from '@/engine/run'
import { f2, f3, sign } from '@/lib/format'
import { cn } from '@/lib/utils'

export default function Costing({ data }: { data: SimData }) {
  const { result: r, input, ctx } = data
  const snap = resolveSnapshot(ctx, input)
  const ref = getProduct(ctx, input.referenceId)
  const refLines = costLines(ref, snap)
  const sulph = r.lines.find((l) => l.id === 'sulphur')?.usd ?? 0
  const diff = r.refCost != null ? r.unitCost - r.refCost : null
  const extra = (x: { dna: number; marketing: number }) => [...(x.dna ? [{ label: 'D&A', usd: x.dna }] : []), ...(x.marketing ? [{ label: 'Marketing', usd: x.marketing }] : [])]
  return (
    <div className="space-y-12">
      <div className="grid grid-cols-2 gap-4 @2xl:grid-cols-4">
        <Kpi label="Unit cost" value={f2(r.unitCost)} unit="USD/t" delta={r.name} />
        <Kpi label={`${input.referenceId} unit cost`} value={f2(r.refCost)} unit="USD/t" delta={input.refCostOverride != null && snap.id === 'today' ? 'Deck figure (you chose)' : snap.id === 'today' ? 'Standard cost 2026' : `CRU · ${snap.label}`} />
        <Kpi label="Difference" value={diff == null ? '—' : sign(diff)} unit="USD/t" delta={diff == null ? '' : diff < 0 ? '▼ raw-material savings' : '▲ higher than reference'} />
        <Kpi label="Sulphur share of cost" value={r.unitCost ? String(Math.round((sulph / r.unitCost) * 100)) : '—'} unit="%" delta={`${f2(sulph)} of ${f2(r.unitCost)} USD/t`} />
      </div>
      <Card title="Cost build-up by ingredient" sub={`USD per t of product · input prices for ${snap.id === 'today' ? 'the current year' : snap.label}`}>
        <CostStack rows={[{ label: r.name, lines: r.lines, extra: extra(r) }, { label: `${input.referenceId} (reference)`, lines: refLines, extra: extra({ dna: r.dna, marketing: 0 }) }]} />
        <div className="mt-3"><Legend items={ING_LEGEND} /></div>
      </Card>
      <div className="grid gap-4 @4xl:grid-cols-2">
        <Card title="Recipe × input prices" sub="Source: Standard cost · 2026" actions={<SourceChip>Recipes</SourceChip>}>
          <div className="overflow-x-auto">
            <table className="tbl w-full min-w-[420px] text-sm">
              <thead><tr className="border-b text-[13px] text-muted-foreground"><th className="py-2.5 text-left font-medium">Ingredient</th><th className="py-2.5 text-right font-medium">t / t</th><th className="py-2.5 text-right font-medium">USD/t</th><th className="py-2.5 text-right font-medium">USD/t prod.</th></tr></thead>
              <tbody>
                {['ammonia', 'kcl', 'rockDry', 'rockWet', 'sulphur'].map((id) => {
                  const l = r.lines.find((x) => x.id === id)
                  const label = { ammonia: 'Ammonia', kcl: 'KCl', rockDry: 'Rock (dry)', rockWet: 'Rock (wet)', sulphur: 'Sulphur' }[id]!
                  return <tr key={id} className="border-b"><td className="py-3">{label}</td><td className={cn('num py-3 text-right', !l && 'text-subtle')}>{l ? f3(l.qty) : '0'}</td><td className="num py-3 text-right">{snap.inputs[id as keyof typeof snap.inputs]}</td><td className={cn('num py-3 text-right', !l && 'text-subtle')}>{l ? f2(l.usd) : '0.00'}</td></tr>
                })}
                <tr className="border-b"><td className="py-3">Marketing ({Math.round(input.marketingPct * 100)}%)</td><td className="num py-3 text-right text-subtle">—</td><td className="num py-3 text-right text-subtle">—</td><td className="num py-3 text-right">{f2(r.marketing)}</td></tr>
                {input.fullCost && <tr className="border-b"><td className="py-3">Manufacturing & D&A</td><td className="py-3" /><td className="py-3" /><td className="num py-3 text-right">{f2(r.dna)}</td></tr>}
                <tr className="bg-muted/60 font-medium"><td className="py-3 pl-2">Total</td><td /><td /><td className="num py-3 pr-0 text-right">{f2(r.unitCost)}</td></tr>
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Input prices 2026 → 2034" sub="USD/t · Standard cost outlook"><TrendLines /></Card>
      </div>
    </div>
  )
}
