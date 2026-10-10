import { AlertTriangle, Check, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { NumberField } from '@/components/app/NumberField'
import type { IngredientId, Product, YieldUnit } from '@/engine/types'
import { dayLong, f2 } from '@/lib/format'
import { ApiError, api, report } from '@/lib/api'
import { useDebounced, useQuery } from '@/lib/query'
import { useApp } from '@/store/app'

const blank = (): Product => ({ id: 'new', name: '', family: 'phosfusion', recipe: { rockDry: 0, rockWet: 0, sulphur: 0 }, composition: { N: 0, P2O5: 0, K2O: 0, S: 0 }, pcf: null, appRate: null, yieldGain: null, yieldGainUnit: 't/ha', baselineYield: null })

/** The sheet around the form. The form is mounted per product, so it never shows the figures of the one before. */
export function ProductSheet() {
  const id = useApp((s) => s.ui.productSheetId); const setUI = useApp((s) => s.setUI); const dirty = useApp((s) => s.ui.dirty)
  const products = useApp((s) => s.products)
  const initial = useMemo(() => (id === 'new' || !id ? blank() : structuredClone(products.find((x) => x.id === id) ?? blank())), [id]) // eslint-disable-line react-hooks/exhaustive-deps
  // Escape, the close button and a click outside all come here: changes are not lost without a word.
  const close = () => { if (!dirty || window.confirm('Close without saving your changes?')) setUI({ productSheetId: null, dirty: false }) }
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && close()}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[480px]">
        <SheetDescription className="sr-only">Edit product recipe, composition, footprint and agronomy</SheetDescription>
        {id && <ProductForm key={id} id={id} initial={initial} onClose={close} />}
      </SheetContent>
    </Sheet>
  )
}

function ProductForm({ id, initial, onClose }: { id: string; initial: Product; onClose: () => void }) {
  const setUI = useApp((s) => s.setUI); const upsert = useApp((s) => s.upsertProduct)
  const INGREDIENTS = useApp((s) => s.ingredients); const L = useApp((s) => s.limits)
  const isNew = id === 'new'
  const [p, setP] = useState<Product>(initial)
  const [saving, setSaving] = useState(false)
  const [refused, setRefused] = useState<Record<string, string>>({}) // what the server said on Save

  const dirty = JSON.stringify(p) !== JSON.stringify(initial)
  useEffect(() => { setUI({ dirty }) }, [dirty]) // eslint-disable-line react-hooks/exhaustive-deps

  // A moment after the last keystroke the server prices the recipe and checks the product: the same rules and prices as on Save and in a run.
  const now = JSON.stringify(p)
  const settled = useDebounced(now)
  const fresh = settled === now
  const recipe = JSON.stringify(JSON.parse(settled).recipe)
  const cost = useQuery(`recipe:${recipe}`, () => api.recipeCost(JSON.parse(recipe)))
  const checked = useQuery(`check:${id}:${settled}`, () => api.validateProduct(JSON.parse(settled), isNew ? undefined : id))
  const errors: Record<string, string> = { ...Object.fromEntries((checked.data?.errors ?? []).map((e) => [e.field, e.message])), ...refused }
  const err = (field: string) => errors[field] ?? null
  const blocked = saving || !fresh || checked.loading || Object.keys(errors).length > 0 || !!checked.error

  const lines = Object.entries(p.recipe) as [IngredientId, number][]
  const line = (k: IngredientId) => (fresh ? cost.data?.lines.find((l) => l.id === k) : undefined)
  const sum = p.composition.N + p.composition.P2O5 + p.composition.K2O + p.composition.S
  const available = INGREDIENTS.filter((i) => !(i.id in p.recipe))
  const change = (patch: Partial<Product>) => { setRefused({}); setP({ ...p, ...patch }) }
  const save = async () => {
    setSaving(true)
    let out: Product
    try { out = await upsert(p, isNew) } catch (e) {
      // The server decides. What it refuses is shown on the fields, like the checks made while typing.
      if (e instanceof ApiError && e.fields.length) setRefused(Object.fromEntries(e.fields.map((f) => [f.field, f.message]))); else report(e)
      setSaving(false); return
    } // a new product gets its id from the backend
    setUI({ productSheetId: null, dirty: false }); toast(`${out.name} saved`, { description: 'Existing runs are untouched. Re-run to use the new recipe.' })
  }
  const total = !fresh || cost.loading ? '…' : cost.data?.rawMaterial != null ? f2(cost.data.rawMaterial) : 'Unavailable'
  return (
    <>
      <div className="flex h-16 shrink-0 flex-col justify-center border-b pl-5 pr-14">
        <SheetTitle className="text-base">{isNew ? 'New product' : p.name || 'Product'}</SheetTitle>
        <p className="text-[13px] text-muted-foreground">{isNew ? 'Add a product to the library' : 'Edit product · changes apply to new runs only'}</p>
      </div>
      <form className="flex min-h-0 flex-1 flex-col" noValidate onSubmit={(e) => { e.preventDefault(); if (!blocked) void save() }}>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {initial.status === 'quarantined' && (
            <div className="rounded-lg bg-warning-bg p-3 text-[13px] text-warning-fg" role="status">
              <div className="flex items-center gap-1.5 font-medium"><AlertTriangle className="size-3.5" />Set aside for review: it cannot be priced until it is corrected</div>
              <ul className="mt-1 list-disc pl-5">{(initial.issues ?? []).map((i) => <li key={i}>{i}</li>)}</ul>
            </div>
          )}
          {isNew && (
            <div>
              <label htmlFor="product-name" className="mb-1.5 block text-sm font-medium">Name</label>
              <Input id="product-name" aria-label="Product name" value={p.name} maxLength={L.productNameMax} aria-invalid={!!err('name')} aria-describedby={err('name') ? 'product-name-error' : undefined} onChange={(e) => change({ name: e.target.value })} placeholder="e.g. Phosfusion 70-30" />
              {err('name') && p.name !== '' && <p id="product-name-error" role="alert" className="mt-1 text-[12px] text-danger-fg">Name {err('name')}</p>}
            </div>
          )}
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Recipe</h4><span className="text-[13px] text-muted-foreground">t of ingredient per t of product · at most {L.recipeQtyMax} each</span></div>
            <div className="overflow-hidden rounded-lg border">
              <table className="tbl tbl-flush w-full text-[13px]"><thead className="bg-muted text-muted-foreground"><tr><th className="px-2.5 py-2 text-left font-medium">Ingredient</th><th className="px-2.5 py-2 text-right font-medium">t / t</th><th className="px-2.5 py-2 text-right font-medium">USD/t</th><th className="px-2.5 py-2 text-right font-medium">USD/t prod.</th></tr></thead>
                <tbody>{lines.map(([k, q]) => {
                  const l = line(k); const name = INGREDIENTS.find((i) => i.id === k)?.label ?? k
                  return (
                    <tr key={k} className="border-t align-top"><td className="px-2.5 py-2 text-sm">{name}</td>
                      <td className="px-2.5 py-1.5"><NumberField hideLabel label={`${name} quantity`} className="ml-auto w-[104px]" inputClassName="h-7 px-2 text-right text-[13px]" value={q} min={0} max={L.recipeQtyMax} step={0.001} required error={err(`recipe.${k}`)} onChange={(v) => change({ recipe: { ...p.recipe, [k]: v ?? NaN } })} /></td>
                      <td className="num px-2.5 py-2 text-right">{l ? (l.price ?? <span className="text-warning-fg">no price</span>) : '—'}</td>
                      <td className="num px-2.5 py-2 text-right">{l ? (l.usd == null ? '—' : f2(l.usd)) : q > 0 ? '…' : '—'}</td></tr>
                  )
                })}</tbody></table>
              {available.length > 0 && (
                <Select value="" onValueChange={(v) => change({ recipe: { ...p.recipe, [v]: 0 } })}>
                  <SelectTrigger className="h-9 w-full justify-start gap-1.5 rounded-none border-0 border-t text-[13px] font-medium shadow-none" aria-label="Add ingredient"><Plus className="size-3.5" /><SelectValue placeholder="Add ingredient" /></SelectTrigger>
                  <SelectContent>{available.map((i) => <SelectItem key={i.id} value={i.id}>{i.label}</SelectItem>)}</SelectContent>
                </Select>)}
            </div>
            {err('recipe') && <p role="alert" className="text-[12px] text-danger-fg">Recipe {err('recipe')}</p>}
          </section>
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Composition</h4><span className="text-[13px] text-muted-foreground">typed in · lab-confirmed</span></div>
            <div className="grid grid-cols-4 gap-2">{([['N', 'N'], ['P2O5', 'P₂O₅'], ['K2O', 'K₂O'], ['S', 'S']] as const).map(([k, l]) => (
              <NumberField key={k} label={l} unit="%" scale={100} min={0} max={1} step={0.01} required value={p.composition[k]} error={err(`composition.${k}`)} onChange={(v) => change({ composition: { ...p.composition, [k]: v ?? NaN } })} />
            ))}</div>
            <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground" role={err('composition') ? 'alert' : undefined}>{!err('composition') && sum <= L.nutrientTotalMax ? <Check className="size-3.5 text-foreground" /> : <AlertTriangle className="size-3.5 text-warning-fg" />}Nutrients sum to {(sum * 100).toFixed(2)}% — {err('composition') ?? `at most ${L.nutrientTotalMax * 100}%`}</div>
          </section>
          <section className="space-y-2">
            <h4 className="text-sm font-semibold">Footprint</h4>
            <div className="flex items-start gap-3">
              <NumberField label="Carbon footprint" unit="t CO₂/t" className="w-[190px]" min={0} max={L.pcfMax} step={0.01} placeholder="—" value={p.pcf} error={err('pcf')} onChange={(v) => change({ pcf: v, pcfPlaceholder: false })} />
              {p.pcfPlaceholder && <span className="mt-7 flex items-center gap-1.5 text-[13px] font-medium text-warning-fg"><AlertTriangle className="size-3.5" />Placeholder value</span>}
            </div>
          </section>
          <section className="space-y-2">
            <div className="flex items-baseline justify-between"><h4 className="text-sm font-semibold">Agronomy</h4><span className="text-[13px] text-muted-foreground">from Agro tests</span></div>
            <div className="grid grid-cols-2 gap-2">
              <NumberField label="Application rate" unit="t/ha" min={0} above max={L.appRateMax} step={0.001} placeholder="—" value={p.appRate} error={err('appRate')} onChange={(v) => change({ appRate: v })} />
              <div>
                <label htmlFor="yield-unit" className="mb-1 block text-[13px] text-muted-foreground">Yield gain is in</label>
                {/* The unit is stored with the value: a number alone is never read as t/ha or as %. */}
                <Select value={p.yieldGainUnit ?? ''} onValueChange={(v) => change({ yieldGainUnit: v as YieldUnit, baselineYield: v === '%' ? p.baselineYield ?? null : null })}>
                  <SelectTrigger id="yield-unit" className="w-full" aria-label="Yield gain unit"><SelectValue placeholder="Unit not set" /></SelectTrigger>
                  <SelectContent><SelectItem value="t/ha">t of crop per ha</SelectItem><SelectItem value="%">% of the baseline yield</SelectItem></SelectContent>
                </Select>
              </div>
              <NumberField label="Yield gain vs reference" unit={p.yieldGainUnit ?? '?'} min={0} max={p.yieldGainUnit === '%' ? L.yieldGainMaxPct : L.yieldGainMaxTHa} step={0.01} placeholder="—" value={p.yieldGain} error={err('yieldGain')} onChange={(v) => change({ yieldGain: v })} />
              {p.yieldGainUnit === '%' && <NumberField label="Baseline yield" unit="t/ha" min={0} above max={L.baselineYieldMax} step={0.01} placeholder="—" value={p.baselineYield ?? null} error={err('baselineYield')} onChange={(v) => change({ baselineYield: v })} />}
            </div>
            {p.yieldGain != null && !p.yieldGainUnit && <p className="flex items-center gap-1.5 text-[13px] text-warning-fg"><AlertTriangle className="size-3.5" />The unit of this yield gain was never stored. Runs use it as t/ha and flag it until you set it.</p>}
          </section>
        </div>
        <div className="flex min-h-16 shrink-0 items-center gap-2 border-t px-5 py-2">
          <div className="min-w-0">
            <div className="text-[13px] text-muted-foreground">Raw-material cost</div>
            <div className="flex items-end gap-1"><span className="num text-lg font-semibold" data-testid="live-cost">{total}</span>{cost.data?.rawMaterial != null && fresh && <span className="pb-0.5 text-[13px] text-muted-foreground">USD/t</span>}</div>
            {/* Where the prices come from, or why there is no total: never a 0.00 that is not a cost. */}
            <div className="truncate text-[12px] text-muted-foreground" data-testid="cost-source" title={cost.data?.source}>{cost.error ? `Unavailable: ${cost.error}` : cost.data?.unavailable ?? (cost.data ? `${cost.data.snapshotLabel} prices · as of ${dayLong(cost.data.asOf)} · ${cost.data.source}` : '')}</div>
          </div>
          <span className="flex-1" /><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={blocked} title={Object.keys(errors).length ? 'Correct the fields marked in red' : undefined}>Save product</Button>
        </div>
      </form>
    </>
  )
}
