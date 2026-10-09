import { AlertTriangle, Check, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { INGREDIENTS } from '@/engine/run'
import type { IngredientId, Product } from '@/engine/types'
import { f2 } from '@/lib/format'
import { report } from '@/lib/api'
import { useApp } from '@/store/app'

const blank = (): Product => ({ id: 'new-' + Math.random().toString(36).slice(2, 7), name: '', family: 'phosfusion', recipe: { rockDry: 0, rockWet: 0, sulphur: 0 }, composition: { N: 0, P2O5: 0, K2O: 0, S: 0 }, pcf: null, appRate: null, yieldGain: null })

export function ProductSheet() {
  const id = useApp((s) => s.ui.productSheetId); const setUI = useApp((s) => s.setUI)
  const products = useApp((s) => s.products); const upsert = useApp((s) => s.upsertProduct)
  const [p, setP] = useState<Product>(blank())
  useEffect(() => { if (id) setP(id === 'new' ? blank() : structuredClone(products.find((x) => x.id === id) ?? blank())) }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  const snap = useApp((s) => s.snapshots[0])
  const lines = (Object.entries(p.recipe) as [IngredientId, number][])
  const total = lines.reduce((a, [k, q]) => a + (q || 0) * (snap.inputs[k] ?? 0), 0)
  const sum = p.composition.N + p.composition.P2O5 + p.composition.K2O + p.composition.S
  const num = (v: string) => { const n = parseFloat(v); return Number.isNaN(n) ? 0 : n }
  const available = INGREDIENTS.filter((i) => !(i.id in p.recipe))
  const save = async () => {
    if (!p.name.trim()) { toast('Give the product a name'); return }
    const out = { ...p, id: id === 'new' ? p.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') : p.id }
    try { await upsert(out, id === 'new') } catch (e) { report(e); return }
    setUI({ productSheetId: null }); toast(`${out.name} saved`, { description: 'Existing runs are untouched. Re-run to use the new recipe.' })
  }
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && setUI({ productSheetId: null })}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[480px]">
        <SheetDescription className="sr-only">Edit product recipe, composition, footprint and agronomy</SheetDescription>
        <div className="flex h-16 shrink-0 flex-col justify-center border-b pl-5 pr-14">
          <SheetTitle className="text-base">{id === 'new' ? 'New product' : p.name || 'Product'}</SheetTitle>
          <p className="text-[13px] text-muted-foreground">{id === 'new' ? 'Add a product to the library' : 'Edit product · changes apply to new runs only'}</p>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {id === 'new' && <div><label className="mb-1.5 block text-sm font-medium">Name</label><Input aria-label="Product name" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} placeholder="e.g. Phosfusion 70-30" /></div>}
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Recipe</h4><span className="text-[13px] text-muted-foreground">t of ingredient per t of product</span></div>
            <div className="overflow-hidden rounded-lg border">
              <table className="tbl tbl-flush w-full text-[13px]"><thead className="bg-muted text-muted-foreground"><tr><th className="px-2.5 py-2 text-left font-medium">Ingredient</th><th className="px-2.5 py-2 text-right font-medium">t / t</th><th className="px-2.5 py-2 text-right font-medium">USD/t 2026</th><th className="px-2.5 py-2 text-right font-medium">USD/t prod.</th></tr></thead>
                <tbody>{lines.map(([k, q]) => (
                  <tr key={k} className="border-t"><td className="px-2.5 py-1.5 text-sm">{INGREDIENTS.find((i) => i.id === k)?.label ?? k}</td>
                    <td className="px-2.5 py-1.5 text-right"><Input aria-label={`${k} quantity`} inputMode="decimal" className="num ml-auto h-7 w-[84px] px-2 text-right text-[13px]" value={String(q ?? 0)} onChange={(e) => setP({ ...p, recipe: { ...p.recipe, [k]: num(e.target.value) } })} /></td>
                    <td className="num px-2.5 py-1.5 text-right">{snap.inputs[k]}</td><td className="num px-2.5 py-1.5 text-right">{f2((q || 0) * (snap.inputs[k] ?? 0))}</td></tr>))}
                </tbody></table>
              {available.length > 0 && (
                <Select value="" onValueChange={(v) => setP({ ...p, recipe: { ...p.recipe, [v]: 0 } })}>
                  <SelectTrigger className="h-9 w-full justify-start gap-1.5 rounded-none border-0 border-t text-[13px] font-medium shadow-none" aria-label="Add ingredient"><Plus className="size-3.5" /><SelectValue placeholder="Add ingredient" /></SelectTrigger>
                  <SelectContent>{available.map((i) => <SelectItem key={i.id} value={i.id}>{i.label}</SelectItem>)}</SelectContent>
                </Select>)}
            </div>
          </section>
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Composition</h4><span className="text-[13px] text-muted-foreground">typed in · lab-confirmed</span></div>
            <div className="grid grid-cols-4 gap-2">{([['N', 'N %'], ['P2O5', 'P₂O₅ %'], ['K2O', 'K₂O %'], ['S', 'S %']] as const).map(([k, l]) => (
              <div key={k}><div className="mb-1 text-[13px] text-muted-foreground">{l}</div><Input aria-label={l} inputMode="decimal" className="num" value={String(Math.round(p.composition[k] * 10000) / 100)} onChange={(e) => setP({ ...p, composition: { ...p.composition, [k]: num(e.target.value) / 100 } })} /></div>
            ))}</div>
            <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground">{sum <= 1 ? <Check className="size-3.5 text-foreground" /> : <AlertTriangle className="size-3.5 text-warning-fg" />}Nutrients sum to {(sum * 100).toFixed(2)}% — {sum <= 1 ? 'within range' : 'above 100%, check the values'}</div>
          </section>
          <section className="space-y-2">
            <h4 className="text-sm font-semibold">Footprint</h4>
            <div className="flex items-center gap-3">
              <div className="relative w-[170px]"><Input aria-label="Carbon footprint" inputMode="decimal" className={`num pr-16 ${p.pcfPlaceholder ? 'border-warning-dot' : ''}`} value={p.pcf == null ? '' : String(p.pcf)} placeholder="—" onChange={(e) => setP({ ...p, pcf: e.target.value === '' ? null : num(e.target.value), pcfPlaceholder: false })} /><span className="absolute right-3 top-2 text-[13px] text-muted-foreground">t CO₂/t</span></div>
              {p.pcfPlaceholder && <span className="flex items-center gap-1.5 text-[13px] font-medium text-warning-fg"><AlertTriangle className="size-3.5" />Placeholder value</span>}
            </div>
          </section>
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Agronomy</h4><span className="text-[13px] text-muted-foreground">from Agro tests</span></div>
            <div className="grid grid-cols-2 gap-2">
              <div><div className="mb-1 text-[13px] text-muted-foreground">Application rate</div><div className="relative"><Input aria-label="Application rate" inputMode="decimal" className="num pr-12" value={p.appRate == null ? '' : String(p.appRate)} placeholder="—" onChange={(e) => setP({ ...p, appRate: e.target.value === '' ? null : num(e.target.value) })} /><span className="absolute right-3 top-2 text-[13px] text-muted-foreground">t/ha</span></div></div>
              <div><div className="mb-1 text-[13px] text-muted-foreground">Yield gain vs reference</div><div className="relative"><Input aria-label="Yield gain" inputMode="decimal" className="num pr-12" value={p.yieldGain == null ? '' : String(p.yieldGain)} placeholder="—" onChange={(e) => setP({ ...p, yieldGain: e.target.value === '' ? null : num(e.target.value) })} /><span className="absolute right-3 top-2 text-[13px] text-muted-foreground">t/ha</span></div></div>
            </div>
          </section>
        </div>
        <div className="flex h-16 shrink-0 items-center gap-2 border-t px-5">
          <div><div className="text-[13px] text-muted-foreground">Unit cost · 2026</div><div className="flex items-end gap-1"><span className="num text-lg font-semibold" data-testid="live-cost">{f2(total)}</span><span className="pb-0.5 text-[13px] text-muted-foreground">USD/t</span></div></div>
          <span className="flex-1" /><Button variant="ghost" onClick={() => setUI({ productSheetId: null })}>Cancel</Button><Button onClick={save}>Save product</Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
export { X }
