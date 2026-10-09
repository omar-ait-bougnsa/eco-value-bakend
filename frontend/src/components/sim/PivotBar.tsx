import { Pin } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { METHOD_LABEL } from '@/engine/run'
import { useApp } from '@/store/app'
import type { PinAxis } from '@/store/types'
import { cn } from '@/lib/utils'
import { METRIC_LABEL } from './PivotTable'
import type { SimData } from './sim-context'

export const chipTrigger = 'h-[28px] min-w-0 gap-1 border-0 bg-transparent px-1.5 py-0 text-sm font-medium shadow-none focus:ring-0 focus-visible:ring-0 [&_svg]:size-3'

function PivotChip({ axis, label, pinned, onPin, children }: { axis: PinAxis; label: string; pinned: boolean; onPin: () => void; children: React.ReactNode }) {
  return (
    <div className={cn('inline-flex h-[30px] items-center gap-1 rounded-md border bg-background pl-1.5', pinned && 'border-foreground')} data-testid={`pivot-${axis}`}>
      <button onClick={onPin} aria-label={pinned ? `${label} pinned` : `Pin ${label}`} title={pinned ? 'Pinned' : 'Pin this axis'} className={cn('rounded p-1', pinned ? 'text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground')}><Pin className={cn('size-3.5', pinned && 'fill-foreground')} /></button>
      <span className="text-[13px] text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

/** Product / Strategy / Metric: pin one axis and compare across the other two. Lives on the Overview tab only. */
export function PivotBar({ data }: { data: SimData }) {
  const { sim, input, ctx } = data
  const v = sim.view
  const setView = useApp((s) => s.setView)
  const products = input.productIds.map((id) => ctx.products.find((p) => p.id === id)!)
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="pivot-bar">
      <PivotChip axis="product" label="Product" pinned={v.pin === 'product'} onPin={() => setView(sim.id, { pin: 'product' })}>
        <Select value={v.product} onValueChange={(p) => setView(sim.id, { product: p })}><SelectTrigger className={chipTrigger} aria-label="Product"><SelectValue /></SelectTrigger><SelectContent>{products.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent></Select>
      </PivotChip>
      <PivotChip axis="strategy" label="Strategy" pinned={v.pin === 'strategy'} onPin={() => setView(sim.id, { pin: 'strategy' })}>
        <Select value={v.strategy} onValueChange={(p) => setView(sim.id, { strategy: p as never })}><SelectTrigger className={chipTrigger} aria-label="Strategy"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All {input.methods.length}</SelectItem>{input.methods.map((m) => <SelectItem key={m} value={m}>{METHOD_LABEL[m]}</SelectItem>)}</SelectContent></Select>
      </PivotChip>
      <PivotChip axis="metric" label="Metric" pinned={v.pin === 'metric'} onPin={() => setView(sim.id, { pin: 'metric' })}>
        <Select value={v.metric} onValueChange={(p) => setView(sim.id, { metric: p as never })}><SelectTrigger className={chipTrigger} aria-label="Metric"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(METRIC_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent></Select>
      </PivotChip>
    </div>
  )
}
