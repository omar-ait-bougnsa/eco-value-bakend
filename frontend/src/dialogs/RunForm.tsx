import { AlertTriangle, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useMatch, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { startRun } from '@/agent/chat'
import { PeriodPicker } from '@/components/sim/PeriodPicker'
import { periodLabel, samePeriod, ytd } from '@/engine/period'
import { METHOD_LABEL } from '@/engine/run'
import type { Method, RefId, RunInput } from '@/engine/types'
import { useFreshness } from '@/components/app/FreshnessChip'
import { api, report } from '@/lib/api'
import { useDebounced, useQuery } from '@/lib/query'
import { NumberField } from '@/components/app/NumberField'
import { defaultRunInput, useApp, useReferences, uid } from '@/store/app'
import { dayShort } from '@/lib/format'

const L = ({ children }: { children: React.ReactNode }) => <label className="mb-1.5 block text-sm font-medium">{children}</label>

export function RunForm() {
  const open = useApp((s) => s.ui.runFormOpen); const setUI = useApp((s) => s.setUI)
  const params = useApp((s) => s.params); const allProducts = useApp((s) => s.products); const limits = useApp((s) => s.limits)
  const products = allProducts.filter((p) => p.status !== 'quarantined') // a product set aside for review cannot be priced
  const nav = useNavigate(); const m = useMatch('/s/:id')
  const sim = useApp((s) => (m?.params.id ? s.sims[m.params.id] : undefined))
  const fresh = useFreshness(); const refs = useReferences()
  const [f, setF] = useState<RunInput>(() => defaultRunInput(params))
  const [comment, setComment] = useState('')
  useEffect(() => { if (open) { const last = sim?.runs[sim.runs.length - 1]; setF(defaultRunInput(params, last ? { productIds: last.input.productIds, referenceId: last.input.referenceId } : {})); setComment(''); setTouched(false) } }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const [touched, setTouched] = useState(false)
  const set = <K extends keyof RunInput>(k: K, v: RunInput[K]) => { setTouched(true); setF((x) => ({ ...x, [k]: v })) }
  useEffect(() => { setUI({ dirty: open && touched }) }, [open, touched]) // eslint-disable-line react-hooks/exhaustive-deps
  // The server checks the input a moment after the last change, with the rules it applies when the run is made.
  const now = JSON.stringify(f); const settled = useDebounced(now)
  const checked = useQuery(open ? `runcheck:${settled}` : null, () => api.validateRun(JSON.parse(settled)))
  const errors: Record<string, string> = Object.fromEntries((checked.data?.errors ?? []).map((e) => [e.field, e.message]))
  const invalid = settled !== now || checked.loading || !!checked.error || Object.keys(errors).length > 0
  const close = () => { if (!touched || window.confirm('Close without running? Your changes to this form are not kept.')) setUI({ runFormOpen: false, dirty: false }) }
  const dirty = (k: keyof RunInput) => JSON.stringify(f[k]) !== JSON.stringify(defaultRunInput(params)[k])
  const toggleProd = (id: string) => set('productIds', f.productIds.includes(id) ? f.productIds.filter((x) => x !== id) : [...f.productIds, id])
  const run = async () => {
    if (invalid) return
    const st = useApp.getState()
    const last = sim?.runs[sim.runs.length - 1]
    const input: RunInput = { ...f, comment, resolved: last && last.input.referenceId === f.referenceId ? last.input.resolved : {}, refCostOverride: last && last.input.referenceId === f.referenceId ? last.input.refCostOverride : null }
    setUI({ runFormOpen: false, dirty: false })
    const names = f.productIds.map((id) => products.find((p) => p.id === id)!.name.replace('Phosfusion ', '')).join(' & ')
    const title = `${f.productIds.length > 1 ? 'Phosfusion ' + names : products.find((p) => p.id === f.productIds[0])!.name} vs ${f.referenceId}${samePeriod({ from: f.periodFrom, to: f.periodTo }, ytd()) ? '' : ` · ${periodLabel({ from: f.periodFrom, to: f.periodTo })}`}`
    let id = sim?.id
    if (!id || !last) { try { id = await st.createSim(title, input) } catch (e) { report(e); return } }
    const text = `Run: ${title}${comment ? ` — ${comment}` : ''}`
    st.pushMsg(id, { id: uid(), kind: 'user', text })
    st.setUI({ askOpen: true })
    nav(`/s/${id}`)
    void startRun(id, text, input)
  }
  const prodNames = f.productIds.map((id) => products.find((p) => p.id === id)?.name).filter(Boolean)
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? setUI({ runFormOpen: true }) : close())}>
      <DialogContent className="max-h-[92dvh] gap-0 overflow-y-auto p-0 sm:max-w-[560px]">
        <DialogHeader className="space-y-1 p-6 pb-4"><DialogTitle className="text-base">Configure run</DialogTitle><DialogDescription className="text-[13px]">Defaults come from Parameters. Overridden fields show a dot.</DialogDescription></DialogHeader>
        <div className="space-y-4 px-6 pb-4">
          <div>
            <L>Products</L>
            <Popover>
              <PopoverTrigger asChild>
                <button className="flex min-h-[34px] w-full flex-wrap items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-left text-sm" aria-label="Products">
                  {prodNames.length ? prodNames.map((n) => <span key={n} className="rounded-md bg-muted px-2 py-0.5 text-[13px] font-medium">{n}</span>) : <span className="text-muted-foreground">Select products</span>}
                  <span className="ml-auto text-[13px] text-muted-foreground">{f.productIds.length === products.length ? 'All' : ''}</span>
                </button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-[340px] p-1.5">
                <button className="mb-1 w-full rounded px-2 py-1.5 text-left text-[13px] font-medium text-muted-foreground hover:bg-accent" onClick={() => set('productIds', f.productIds.length === products.length ? [products[0].id] : products.map((p) => p.id))}>{f.productIds.length === products.length ? 'Clear' : 'Select all'}</button>
                <div className="max-h-[260px] overflow-y-auto">{products.map((p) => (
                  <label key={p.id} className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-sm hover:bg-accent"><Checkbox checked={f.productIds.includes(p.id)} onCheckedChange={() => toggleProd(p.id)} />{p.name}</label>
                ))}</div>
              </PopoverContent>
            </Popover>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><L>Reference product {dirty('referenceId') && <span className="ml-1">●</span>}</L>
              <Select value={f.referenceId} onValueChange={(v) => set('referenceId', v as RefId)}><SelectTrigger className="w-full" aria-label="Reference product"><SelectValue /></SelectTrigger><SelectContent>{refs.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent></Select></div>
            <div><L>Cost-plus margin {dirty('costPlusMargin') && <span className="ml-1">●</span>}</L>
              <NumberField hideLabel label="Cost-plus margin" unit="%" scale={100} min={0} max={limits.marginMax} step={0.1} required value={f.costPlusMargin} error={errors.costPlusMargin} onChange={(v) => set('costPlusMargin', v ?? NaN)} /></div>
          </div>
          <div><L>Methods</L>
            <div className="flex flex-wrap gap-x-5 gap-y-2">{(['costPlus', 'market', 'value', 'refMinus'] as Method[]).map((mm) => (
              <label key={mm} className="flex cursor-pointer items-center gap-2 text-sm"><Checkbox checked={f.methods.includes(mm)} onCheckedChange={() => set('methods', f.methods.includes(mm) ? f.methods.filter((x) => x !== mm) : [...f.methods, mm])} />{METHOD_LABEL[mm]}</label>
            ))}</div></div>
          <div><L>Analysis period</L>
            <PeriodPicker variant="field" value={{ from: f.periodFrom, to: f.periodTo }} onChange={(p) => setF((x) => ({ ...x, periodFrom: p.from, periodTo: p.to }))} /></div>
          <div><L>Comment</L><Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Why are you running this? (recorded in the audit trail)" className="min-h-[64px] text-sm" /></div>
          <Collapsible>
            <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-lg bg-muted px-3 py-2.5 text-left text-sm"><ChevronRight className="size-3.5 transition-transform group-data-[state=open]:rotate-90" /><span className="font-medium">Advanced</span><span className="text-[13px] text-muted-foreground">Price type · Carbon market · Value share · Full cost</span></CollapsibleTrigger>
            <CollapsibleContent className="grid grid-cols-2 gap-3 pt-3">
              <div><L>Price type {dirty('priceType') && '●'}</L><Select value={f.priceType} onValueChange={(v) => set('priceType', v as 'low' | 'high')}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="low">Low</SelectItem><SelectItem value="high">High</SelectItem></SelectContent></Select></div>
              <div><L>Carbon market {dirty('carbonMarket') && '●'}</L><Select value={f.carbonMarket} onValueChange={(v) => set('carbonMarket', v as 'voluntary' | 'cbam')}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="voluntary">Voluntary</SelectItem><SelectItem value="cbam">CBAM</SelectItem></SelectContent></Select></div>
              <div><L>Value share % {dirty('valueShare') && '●'}</L><NumberField hideLabel label="Value share" unit="%" scale={100} min={0} max={1} step={0.1} required value={f.valueShare} error={errors.valueShare} onChange={(v) => set('valueShare', v ?? NaN)} /></div>
              <div><L>Include D&amp;A (full cost)</L><div className="flex h-9 items-center"><Switch checked={f.fullCost} onCheckedChange={(v) => set('fullCost', v)} /></div></div>
            </CollapsibleContent>
          </Collapsible>
        </div>
        {(() => { const rest = Object.entries(errors).filter(([k]) => !['costPlusMargin', 'valueShare'].includes(k)); return rest.length ? <ul role="alert" className="mx-6 mb-3 rounded-lg bg-danger-bg p-3 text-[13px] text-danger-fg">{rest.map(([k, m]) => <li key={k}>{k}: {m}</li>)}</ul> : null })()}
        <DialogFooter className="items-center gap-3 border-t p-4 sm:justify-between">
          {fresh.d1 ? <span className="flex items-center gap-1.5 text-[13px] font-medium text-warning-fg"><AlertTriangle className="size-3.5" />{fresh.d1.title}</span> : <span className="text-[13px] text-muted-foreground">Data is current</span>}
          <div className="flex gap-2"><Button variant="ghost" onClick={close}>Cancel</Button><Button onClick={() => void run()} disabled={invalid} title={Object.keys(errors).length ? 'Correct the fields marked in red' : undefined}>Run <span className="ml-1 text-[13px] opacity-70">⌘⏎</span></Button></div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
