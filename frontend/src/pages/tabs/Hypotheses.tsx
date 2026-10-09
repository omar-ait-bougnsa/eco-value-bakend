import { AlertTriangle, Pencil } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Card, SourceChip } from '@/components/sim/atoms'
import { PeriodPicker } from '@/components/sim/PeriodPicker'
import type { SimData } from '@/components/sim/sim-context'
import type { RunInput } from '@/engine/types'
import { METHOD_LABEL } from '@/engine/run'
import { f2 } from '@/lib/format'
import { dayShort } from '@/lib/format'
import { report } from '@/lib/api'
import { useApp } from '@/store/app'
import { cn } from '@/lib/utils'

type Kind = 'num' | 'pct' | 'sel' | 'switch' | 'ro'
interface Field { key: keyof RunInput | 'unitCost' | 'addressable'; label: string; unit?: string; kind: Kind; options?: [string, string][]; prov?: string; flag?: 'U1' | 'C2'; step?: number }

export default function Hypotheses({ data, onDone }: { data: SimData; onDone?: () => void }) {
  const { run, sim, result, ctx } = data
  const input = run.input
  const [draft, setDraft] = useState<Partial<RunInput>>({})
  const [comment, setComment] = useState('')
  const addRun = useApp((s) => s.addRun)
  const argus = ctx.uploads.find((u) => /argus/i.test(u.name)); const agro = ctx.uploads.find((u) => u.type === 'agro'); const crop = ctx.uploads.find((u) => u.type === 'crop')
  const wrap = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: Event) => {
      const k = (e as CustomEvent<string>).detail
      const el = wrap.current?.querySelector<HTMLElement>(`[data-key="${k}"]`)
      if (el) { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); el.classList.add('ring-2', 'ring-foreground'); setTimeout(() => el.classList.remove('ring-2', 'ring-foreground'), 1600); el.querySelector<HTMLElement>('input,button')?.focus() }
    }
    window.addEventListener('evs:focus-input', h)
    return () => window.removeEventListener('evs:focus-input', h)
  }, [])
  useEffect(() => setDraft({}), [run.id])

  const val = <K extends keyof RunInput>(k: K): RunInput[K] => (k in draft ? (draft[k] as RunInput[K]) : input[k])
  const edited = (k: keyof RunInput) => k in draft && JSON.stringify(draft[k]) !== JSON.stringify(input[k])
  const set = <K extends keyof RunInput>(k: K, v: RunInput[K]) => setDraft((d) => { const n = { ...d, [k]: v }; if (JSON.stringify(v) === JSON.stringify(input[k])) delete n[k]; return n })

  const sections: { title: string; sub: string; rows: Field[] }[] = useMemo(() => [
    { title: 'Products', sub: 'What is being priced and against what', rows: [
      { key: 'productIds', label: 'New product', kind: 'ro', prov: 'Products' },
      { key: 'referenceId', label: 'Reference product', kind: 'sel', options: [['TSP', 'TSP'], ['DAP', 'DAP'], ['MAP', 'MAP']], prov: `Prices · ${argus ? dayShort(argus.fileDate) : '—'}` },
      { key: 'priceType', label: 'Reference price type', kind: 'sel', options: [['low', 'Low'], ['high', 'High']], prov: 'Parameters' }] },
    { title: 'Costing', sub: 'Built from the recipe × input prices', rows: [
      { key: 'unitCost', label: 'Unit cost', unit: 'USD/t', kind: 'ro', prov: 'Standard cost · 2026' },
      { key: 'marketingPct', label: 'Marketing cost', unit: '% of cost', kind: 'pct', prov: 'Parameters' },
      { key: 'fullCost', label: 'Include manufacturing & D&A', kind: 'switch', prov: 'Parameters' },
      { key: 'dnaPerTon', label: 'D&A', unit: 'USD/t', kind: 'num', prov: 'Standard cost · 2026' }] },
    { title: 'Pricing', sub: 'Method settings', rows: [
      { key: 'costPlusMargin', label: 'Cost-plus margin', unit: '%', kind: 'pct', prov: 'Parameters' },
      { key: 'anchor', label: 'Anchor method', kind: 'sel', options: (['refMinus', 'costPlus', 'value', 'market'] as const).map((m) => [m, METHOD_LABEL[m]] as [string, string]), prov: 'Default' },
      { key: 'benchmark', label: 'Market benchmark', unit: 'USD/t', kind: 'num', prov: 'Not set' }] },
    { title: 'Value pricing', sub: 'Agronomic value created', rows: [
      { key: 'yieldGain', label: 'Yield gain vs reference', unit: 't/ha', kind: 'num', flag: 'U1', prov: `Agro trials · ${agro ? dayShort(agro.fileDate) : '—'}`, step: 0.01 },
      { key: 'appRateNew', label: 'Application rate', unit: 't/ha', kind: 'num', prov: `Agro trials · ${agro ? dayShort(agro.fileDate) : '—'}`, step: 0.001 },
      { key: 'cropPrice', label: 'Crop price', unit: 'USD/t', kind: 'num', prov: `Crop prices · ${crop ? dayShort(crop.fileDate) : '—'}` },
      { key: 'valueShare', label: 'Value share kept by OCP', unit: '%', kind: 'pct', prov: 'Parameters' }] },
    { title: 'Carbon', sub: 'Optional — excluded while the price is 0', rows: [
      { key: 'pcfNew', label: 'Product carbon footprint', unit: 't CO₂/t', kind: 'num', flag: 'C2', prov: 'Placeholder', step: 0.01 },
      { key: 'pcfRef', label: 'Reference carbon footprint', unit: 't CO₂/t', kind: 'num', prov: 'Standard PCFs', step: 0.01 },
      { key: 'appRateRef', label: 'Reference application rate', unit: 't/ha', kind: 'num', prov: `Agro trials · ${agro ? dayShort(agro.fileDate) : '—'}`, step: 0.001 },
      { key: 'carbonMarket', label: 'Carbon market', kind: 'sel', options: [['voluntary', 'Voluntary'], ['cbam', 'CBAM']], prov: 'Parameters' },
      { key: 'carbonPrice', label: 'Carbon price', unit: 'USD/t CO₂', kind: 'num', prov: 'Not set' }] },
    { title: 'Volume', sub: 'Addressable market × share', rows: [
      { key: 'addressable', label: 'Addressable market', unit: 't', kind: 'ro', prov: 'Demand model' },
      { key: 'marketShare', label: 'Market share captured', unit: '%', kind: 'pct', prov: 'Agent assumption' },
      { key: 'rampTargetYear', label: 'Ramp-up target year', kind: 'num', prov: 'Parameters', step: 1 }] },
  ], [argus, agro, crop])

  const nChanges = Object.keys(draft).filter((k) => k !== 'periodTo').length
  const changedNames = Object.keys(draft).filter((k) => k !== 'periodTo').map((k) => k === 'periodFrom' ? 'Analysis period' : sections.flatMap((s) => s.rows).find((r) => r.key === k)?.label ?? (k === 'resolved' ? 'Flag confirmation' : k))
  const rerun = () => {
    const changed = Object.keys(draft)
    const next = { ...input, ...draft, comment: comment || 'Edited hypotheses' } as RunInput
    addRun(sim.id, next, 'user', changed.length ? `Edited ${changedNames.map((n) => n.toLowerCase()).join(', ')}` : 'Re-run').catch(report)
    setDraft({}); setComment(''); onDone?.()
  }
  const confirm = (code: 'U1' | 'C2') => setDraft((d) => ({ ...d, resolved: { ...(d.resolved ?? input.resolved), [code]: true } }))

  const renderValue = (f: Field) => {
    const k = f.key as keyof RunInput
    if (f.kind === 'ro') {
      const text = f.key === 'unitCost' ? f2(result.unitCost) : f.key === 'addressable' ? input.addressable.toLocaleString('en-US') : input.productIds.map((id) => ctx.products.find((p) => p.id === id)?.name).join(', ')
      return <span className="num inline-flex h-7 items-center rounded-md bg-muted px-2 text-sm">{text}</span>
    }
    if (f.kind === 'sel') return (
      <Select value={String(val(k))} onValueChange={(v) => set(k, v as never)}>
        <SelectTrigger size="sm" className="h-7 min-w-[130px] text-sm" aria-label={f.label}><SelectValue /></SelectTrigger>
        <SelectContent>{f.options!.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
      </Select>
    )
    if (f.kind === 'switch') return <Switch checked={!!val(k)} onCheckedChange={(v) => set(k, v as never)} aria-label={f.label} />
    const raw = val(k) as number | null
    const display = raw == null ? '' : f.kind === 'pct' ? String(Math.round((raw as number) * 1000) / 10) : String(raw)
    return (
      <Input
        key={`${k}-${run.id}-${edited(k)}`}
        inputMode="decimal" defaultValue={display} placeholder="—"
        aria-label={f.label}
        onChange={(e) => {
          const t = e.target.value.trim()
          if (t === '') { set(k, (k === 'benchmark' ? null : 0) as never); return }
          const n = parseFloat(t); if (Number.isNaN(n)) return
          set(k, (f.kind === 'pct' ? n / 100 : n) as never)
        }}
        className={cn('num h-7 w-[104px] px-2 text-right text-sm', edited(k) && 'border-foreground')}
      />
    )
  }

  return (
    <div ref={wrap} className="space-y-4">
      {nChanges > 0 && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-[10px] border border-foreground bg-background px-4 py-2.5" data-testid="staged-bar">
          <Pencil className="size-3.5" />
          <span className="text-sm font-medium">{nChanges} staged change{nChanges > 1 ? 's' : ''}</span>
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{changedNames.join(' · ')}</span>
          <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Reason (audit trail)" className="h-7 w-[200px] text-sm" />
          <Button size="sm" variant="ghost" onClick={() => setDraft({})}>Discard</Button>
          <Button size="sm" onClick={rerun}>Re-run (v{sim.runs.length + 1})</Button>
        </div>
      )}
      <div className="grid gap-4 @5xl:grid-cols-2">
        <div data-key="period" className="rounded-xl transition-shadow @5xl:col-span-2">
          <Card title="Analysis period" sub="The date range to analyse: a day, a month, a year or any range. Prices and costs are the day-weighted average of the data inside it.">
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-[360px] max-w-full"><PeriodPicker variant="field" value={{ from: val('periodFrom'), to: val('periodTo') }} onChange={(p) => { set('periodFrom', p.from); set('periodTo', p.to) }} /></div>
              {('periodFrom' in draft || 'periodTo' in draft) ? <span className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-[3px] font-mono text-[13px] font-medium"><span className="size-1.5 rounded-full bg-foreground" />You edited</span> : <SourceChip>Parameters</SourceChip>}
            </div>
          </Card>
        </div>
        {sections.map((s) => (
          <Card key={s.title} title={s.title} sub={s.sub}>
            <div>
              {s.rows.map((f) => {
                const k = f.key as keyof RunInput
                const ed = f.kind !== 'ro' && edited(k)
                const flagActive = f.flag && !(draft.resolved ?? input.resolved)[f.flag]
                return (
                  <div key={String(f.key)} data-key={String(f.key)} className="flex items-center gap-3 border-b py-2.5 last:border-b-0 rounded-md transition-shadow">
                    <div className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
                      <span className={cn(f.kind === 'ro' && 'text-muted-foreground')}>{f.label}</span>
                      {flagActive && <AlertTriangle className="size-3.5 shrink-0 text-warning-fg" />}
                    </div>
                    {ed && <span className="num text-[13px] text-muted-foreground line-through">{f.kind === 'pct' ? `${Math.round((input[k] as number) * 1000) / 10}` : String(input[k] ?? '—')}</span>}
                    {renderValue(f)}
                    <span className="hidden w-[68px] text-[13px] text-muted-foreground sm:block">{f.unit}</span>
                    <span className="hidden w-[150px] justify-end sm:flex">
                      {ed ? <span className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-[3px] font-mono text-[13px] font-medium"><span className="size-1.5 rounded-full bg-foreground" />You edited</span>
                        : f.prov === 'Agent assumption' ? <span className="rounded-md bg-warning-bg px-2 py-[3px] font-mono text-[13px] font-medium text-warning-fg">Agent assumption</span>
                          : f.prov ? <SourceChip>{f.prov}</SourceChip> : null}
                    </span>
                    {flagActive && <Button size="sm" variant="outline" onClick={() => confirm(f.flag!)}>{f.flag === 'U1' ? 'Confirm t/ha' : 'Accept'}</Button>}
                  </div>
                )
              })}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
