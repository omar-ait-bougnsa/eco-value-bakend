import { PanelLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { Parameters } from '@/engine/types'
import { useApp, useReferences } from '@/store/app'
import { toast } from 'sonner'

type Row = { key: keyof Parameters; label: string; desc: string; kind: 'pct' | 'num' | 'switch' | 'sel'; unit?: string; options?: [string, string][] }
const SECTIONS: { title: string; sub: string; rows: Row[] }[] = [
  { title: 'Defaults', sub: 'Used when a run does not override them', rows: [
    { key: 'costPlusMargin', label: 'Cost-plus margin', desc: 'Margin added on top of unit cost', kind: 'pct', unit: '%' },
    { key: 'fullCost', label: 'Include manufacturing & D&A', desc: '', kind: 'switch' },
    { key: 'valueShare', label: 'Value share kept by OCP', desc: 'Share of the crop value created that OCP prices in', kind: 'pct', unit: '%' },
    { key: 'marketShare', label: 'Market share captured', desc: 'Used for volume and total margin', kind: 'pct', unit: '%' },
    { key: 'rampTargetYear', label: 'Ramp-up target year', desc: 'Year the market share is reached', kind: 'num' },
    { key: 'priceType', label: 'Reference price type', desc: 'Low or high Argus quote', kind: 'sel', options: [['low', 'Low'], ['high', 'High']] },
    { key: 'carbonMarket', label: 'Carbon market', desc: 'Used when a carbon price is set', kind: 'sel', options: [['voluntary', 'Voluntary'], ['cbam', 'CBAM']] },
    { key: 'defaultReference', label: 'Default reference product', desc: 'Pre-selected in the Run form', kind: 'sel' }] }, // its options are the backend's reference products
  { title: 'Data freshness', sub: 'When to warn about older data', rows: [
    { key: 'freshnessMonths', label: 'Discrepancy threshold', desc: 'Warn when prices and freight are this far apart', kind: 'num', unit: 'months' },
    { key: 'staleDays', label: 'Stale after', desc: 'Warn when the latest upload is older than', kind: 'num', unit: 'days' }] },
]

export default function ParametersPage() {
  const DEFAULT_PARAMS = useApp((s) => s.defaultParams)
  const params = useApp((s) => s.params); const setParams = useApp((s) => s.setParams); const ui = useApp((s) => s.ui); const setUI = useApp((s) => s.setUI)
  const refs = useReferences()
  const render = (r: Row) => {
    const v = params[r.key]
    const options = r.options ?? refs.map((x) => [x, x] as [string, string])
    if (r.kind === 'switch') return <Switch checked={!!v} onCheckedChange={(x) => setParams({ [r.key]: x })} aria-label={r.label} />
    if (r.kind === 'sel') return <Select value={String(v)} onValueChange={(x) => setParams({ [r.key]: x } as Partial<Parameters>)}><SelectTrigger className="w-[150px]" aria-label={r.label}><SelectValue /></SelectTrigger><SelectContent>{options.map(([a, b]) => <SelectItem key={a} value={a}>{b}</SelectItem>)}</SelectContent></Select>
    const disp = r.kind === 'pct' ? String(Math.round((v as number) * 1000) / 10) : String(v)
    return (
      <div className="relative w-[130px]"><Input aria-label={r.label} key={disp} defaultValue={disp} inputMode="decimal" className="num pr-14 text-right" onBlur={(e) => { const n = parseFloat(e.target.value); if (!Number.isNaN(n)) setParams({ [r.key]: r.kind === 'pct' ? n / 100 : n } as Partial<Parameters>) }} /><span className="pointer-events-none absolute right-3 top-2 text-[13px] text-muted-foreground">{r.unit}</span></div>
    )
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="hidden h-14 shrink-0 items-center border-b px-8 md:flex"><button aria-label="Toggle sidebar" onClick={() => setUI({ sidebarOpen: !ui.sidebarOpen })} title="Show or hide the sidebar" className="rounded-md border bg-background p-2 text-foreground hover:bg-accent"><PanelLeft className="size-4" /></button></div>
      <div className="mx-auto w-full max-w-[860px] space-y-6 px-4 py-8 sm:px-8">
        <div className="flex items-center gap-3"><div className="flex-1"><h1 className="text-[28px] font-semibold leading-9 tracking-tight">Parameters</h1><p className="mt-1 text-sm text-muted-foreground">Global defaults. Each run pre-fills from these and can override them.</p></div><Button variant="outline" onClick={() => { setParams(DEFAULT_PARAMS); toast('Parameters reset') }}>Reset all to defaults</Button></div>
        {SECTIONS.map((s) => (
          <section key={s.title} className="rounded-xl border bg-card p-6">
            <h3 className="text-base font-semibold leading-6">{s.title}</h3><p className="mb-2 mt-0.5 text-[13px] text-muted-foreground">{s.sub}</p>
            {s.rows.map((r) => (
              <div key={r.key} className="flex items-center gap-4 border-b py-3 last:border-0">
                <div className="min-w-0 flex-1"><div className="text-sm font-medium">{r.label}</div><div className="text-[13px] text-muted-foreground">{r.key === 'fullCost' ? `Adds ${params.dnaPerTon} USD/t to the unit cost` : r.desc}</div></div>
                {render(r)}
                <button className="inline-flex h-8 shrink-0 items-center rounded-md border bg-background px-3 text-sm font-medium hover:bg-accent" onClick={() => setParams({ [r.key]: DEFAULT_PARAMS[r.key] } as Partial<Parameters>)}>Reset</button>
              </div>
            ))}
          </section>
        ))}
        <section className="rounded-xl border bg-card p-6">
          <h3 className="text-base font-semibold leading-6">Appearance</h3>
          <div className="flex items-center gap-4 py-3"><div className="flex-1"><div className="text-sm font-medium">Theme</div><div className="text-[13px] text-muted-foreground">Follows your system by default</div></div>
            <ToggleGroup type="single" value={ui.theme} onValueChange={(v) => v && setUI({ theme: v as 'system' | 'light' | 'dark' })} variant="outline" size="sm">{['system', 'light', 'dark'].map((t) => <ToggleGroupItem key={t} value={t} className="px-3 text-sm capitalize">{t}</ToggleGroupItem>)}</ToggleGroup></div>
        </section>
      </div>
    </div>
  )
}
