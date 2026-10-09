import type {
  Flag, IngredientId, Method, MethodResult, Parameters, Product, ProductResult, RunInput, RunOutput, Snapshot, UploadFile,
} from './types'
import { DATA_END as TODAY, blendSnapshot, touchesCurrentYear } from './period'

export interface Ctx {
  products: Product[]
  snapshots: Snapshot[]
  uploads: UploadFile[]
  params: Parameters
}

export const INGREDIENTS: { id: IngredientId; label: string }[] = [
  { id: 'ammonia', label: 'Ammonia' },
  { id: 'kcl', label: 'KCl' },
  { id: 'rockDry', label: 'Rock (dry)' },
  { id: 'rockWet', label: 'Rock (wet)' },
  { id: 'sulphur', label: 'Sulphur' },
  { id: 'acp', label: 'ACP (intermediate)' },
]
export const DECK_TSP_COST = 494 // business-case deck, conflicts with Standard cost 655.18

export const METHOD_LABEL: Record<Method, string> = {
  costPlus: 'Cost-plus',
  market: 'Market pricing',
  value: 'Value pricing',
  refMinus: 'Reference minus',
}

const INGREDIENT_LABEL: Record<string, string> = Object.fromEntries(INGREDIENTS.map((i) => [i.id, i.label]))
const N_PER_AMMONIA = 0.82 // t N / t NH3 (matches workbook DAP column)
const K2O_PER_KCL = 0.6
export const CARBON_SCENARIOS = [
  { id: 'vol-low', label: 'Voluntary · low', price: 15 },
  { id: 'vol-high', label: 'Voluntary · high', price: 40 },
  { id: 'cbam', label: 'CBAM / EU-ETS ref.', price: 75 },
]

export function getProduct(ctx: Ctx, id: string): Product {
  const p = ctx.products.find((x) => x.id === id)
  if (!p) throw new Error(`Unknown product ${id}`)
  return p
}
export function getSnapshot(ctx: Ctx, id: string): Snapshot {
  return ctx.snapshots.find((s) => s.id === id) ?? ctx.snapshots[0]
}

/** The market data for a run: a day-weighted blend of the yearly snapshots inside its analysis period. */
export function resolveSnapshot(ctx: Ctx, input: Pick<RunInput, 'periodFrom' | 'periodTo'>): Snapshot {
  return blendSnapshot(ctx.snapshots, { from: input.periodFrom, to: input.periodTo })
}

export function costLines(p: Product, s: Snapshot) {
  return (Object.entries(p.recipe) as [IngredientId, number][])
    .filter(([, q]) => q > 0)
    .map(([id, qty]) => {
      const price = s.inputs[id] ?? 0
      return { id, label: INGREDIENT_LABEL[id] ?? id, qty, price, usd: qty * price }
    })
}

export function refPriceFor(s: Snapshot, ref: RunInput['referenceId'], type: RunInput['priceType']): number | null {
  const q = s.refPrices[ref]
  if (!q) return null
  return (type === 'high' ? q.high ?? q.low : q.low) ?? null
}

export function monthsBetween(a: string, b: string) {
  const d = Math.abs(new Date(a).getTime() - new Date(b).getTime())
  return d / (1000 * 60 * 60 * 24 * 30.4375)
}

export function runProduct(input: RunInput, ctx: Ctx, productId: string): ProductResult {
  const p = getProduct(ctx, productId)
  const ref = getProduct(ctx, input.referenceId)
  const snap = resolveSnapshot(ctx, input)

  const lines = costLines(p, snap)
  const rawMaterial = lines.reduce((a, l) => a + l.usd, 0)
  const dna = input.fullCost ? input.dnaPerTon : 0
  const marketing = input.marketingPct * (rawMaterial + dna)
  const costForMargin = rawMaterial + dna
  const unitCost = costForMargin + marketing

  const refPrice = refPriceFor(snap, input.referenceId, input.priceType)
  const refRaw = costLines(ref, snap).reduce((a, l) => a + l.usd, 0) + dna
  const refCost = input.refCostOverride != null && snap.id === 'today' ? input.refCostOverride : refRaw

  // nutrient unit values (USD / t nutrient)
  const vN = snap.inputs.ammonia / N_PER_AMMONIA
  const vK = snap.inputs.kcl / K2O_PER_KCL
  const vS = snap.inputs.sulphur
  const rc = ref.composition
  const nc = p.composition

  let p2o5ValueRef: number | null = null
  let refMinus: number | null = null
  if (refPrice != null && rc.P2O5 > 0) {
    const pureP = refPrice - rc.N * vN - rc.K2O * vK - rc.S * vS
    p2o5ValueRef = pureP / rc.P2O5
    refMinus = nc.P2O5 * p2o5ValueRef + nc.N * vN + nc.K2O * vK + nc.S * vS
  }

  const addedCrop = input.appRateNew > 0 ? input.yieldGain / input.appRateNew : 0
  const addedValue = addedCrop * input.cropPrice
  const carbonSavingPerHa = input.pcfRef * input.appRateRef - input.pcfNew * input.appRateNew
  const carbonSavingPerT = input.appRateNew > 0 ? carbonSavingPerHa / input.appRateNew : 0
  const carbonEffect = carbonSavingPerT * input.carbonPrice
  const value = refPrice != null ? addedValue * input.valueShare + carbonEffect + refPrice : null
  const costPlus = unitCost * (1 + input.costPlusMargin)

  const prices: Record<Method, number | null> = { costPlus, market: input.benchmark, value, refMinus }
  const anchorPrice = prices[input.anchor] ?? prices.refMinus ?? prices.costPlus
  const floor = costPlus
  const ceiling = value ?? costPlus

  const cgmOf = (price: number | null) => (price == null ? null : price - unitCost + marketing)
  const cgmRef = refPrice != null ? refPrice - refCost : null
  const volume = input.addressable * input.marketShare
  const cgm = cgmOf(anchorPrice)
  const methods: MethodResult[] = (['costPlus', 'refMinus', 'value', 'market'] as Method[])
    .filter((m) => input.methods.includes(m))
    .map((m) => {
      const price = prices[m]
      const c = cgmOf(price)
      return {
        method: m,
        label: METHOD_LABEL[m],
        price,
        cgm: c,
        cgmP2O5: c != null && nc.P2O5 > 0 ? c / nc.P2O5 : null,
        totalMargin: c != null ? c * volume : null,
        deltaVsRef: c != null && cgmRef != null ? c - cgmRef : null,
      }
    })

  const waterfall: ProductResult['waterfall'] = []
  if (cgmRef != null && anchorPrice != null && refPrice != null && cgm != null) {
    const dPrice = anchorPrice - refPrice
    const dCost = refCost - costForMargin
    waterfall.push({ label: `${ref.name} CGM`, from: 0, to: cgmRef, value: cgmRef, kind: 'total' })
    waterfall.push({ label: 'Price vs ' + ref.name, from: cgmRef, to: cgmRef + dPrice, value: dPrice, kind: 'delta' })
    waterfall.push({ label: 'Raw-material savings', from: cgmRef + dPrice, to: cgmRef + dPrice + dCost, value: dCost, kind: 'delta' })
    waterfall.push({ label: 'New product CGM', from: 0, to: cgm, value: cgm, kind: 'total' })
  }

  const ramp = Array.from({ length: 10 }, (_, i) => {
    const year = 2026 + i
    const t = Math.min(Math.max((year - 2026) / Math.max(input.rampTargetYear - 2026, 1), 0), 1)
    return { year, kt: (input.addressable * input.marketShare * t) / 1000 }
  })

  const carbonScenarios = CARBON_SCENARIOS.map((c) => ({ ...c, delta: carbonSavingPerT * c.price }))

  return {
    productId, name: p.name, lines, rawMaterial, dna, marketing, unitCost,
    refPrice, refCost, p2o5ValueRef, addedValue, carbonSavingPerT, carbonEffect,
    prices, anchorPrice, floor, ceiling,
    cgm, cgmRef,
    cgmP2O5: cgm != null && nc.P2O5 > 0 ? cgm / nc.P2O5 : null,
    cgmS: cgm != null && (p.recipe.sulphur ?? 0) > 0 ? cgm / (p.recipe.sulphur as number) : null,
    volume, totalMargin: cgm != null ? cgm * volume : null,
    methods, waterfall, ramp, carbonScenarios,
  }
}

const fmt2 = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function computeFlags(input: RunInput, ctx: Ctx, perProduct: Record<string, ProductResult>): Flag[] {
  const flags: Flag[] = []
  const r = input.resolved
  const snap = resolveSnapshot(ctx, input)
  const lead = perProduct[input.productIds[0]]
  const prod = getProduct(ctx, input.productIds[0])

  if (lead.refPrice == null) {
    flags.push({ id: 'N1', code: 'N1', severity: 'error', title: `No ${input.referenceId} price for ${snap.label}`, detail: 'Pick another reference (DAP, MAP or TSP) or another snapshot.' })
  }

  if (input.referenceId === 'TSP' && snap.id === 'today') {
    if (r.S1) {
      flags.push({ id: 'S1', code: 'S1', severity: 'resolved', title: `TSP full cost set to ${fmt2(lead.refCost ?? 0)} USD/t`, detail: r.S1 === 'deck' ? 'You chose the business-case deck figure.' : 'You chose the Standard cost 2026 figure.' })
    } else {
      flags.push({ id: 'S1', code: 'S1', severity: 'warning', title: 'TSP full production cost differs between sources', detail: `Business-case deck ${DECK_TSP_COST} USD/t vs Standard cost 2026 ${fmt2(lead.refCost ?? 0)} USD/t.`, action: { label: 'Answer', kind: 'answer' } })
    }
  }

  const anchorBelow = Object.values(perProduct).find((x) => x.anchorPrice != null && x.anchorPrice < x.floor)
  if (anchorBelow) {
    flags.push({
      id: 'P1', code: 'P1', severity: r.P1 ? 'resolved' : 'warning',
      title: `Anchor is below the cost-plus floor (${fmt2(anchorBelow.anchorPrice!)} < ${fmt2(anchorBelow.floor)})`,
      detail: 'At this price the margin over cost is thin. Switch the anchor or raise the margin.',
      action: { label: 'Review', kind: 'review', target: 'pricing' },
    })
  }

  const argus = ctx.uploads.filter((u) => u.type === 'prices' && /argus/i.test(u.name)).sort((a, b) => b.dataThrough.localeCompare(a.dataThrough))[0]
  const prices = argus ?? ctx.uploads.filter((u) => u.type === 'prices').sort((a, b) => b.dataThrough.localeCompare(a.dataThrough))[0]
  const freight = ctx.uploads.filter((u) => u.type === 'freight').sort((a, b) => b.dataThrough.localeCompare(a.dataThrough))[0]
  if (prices && freight && touchesCurrentYear({ from: input.periodFrom, to: input.periodTo })) {
    const gap = monthsBetween(prices.dataThrough, freight.dataThrough)
    if (gap >= ctx.params.freshnessMonths) {
      const older = prices.dataThrough < freight.dataThrough ? 'Prices' : 'Freight'
      flags.push({
        id: 'D1', code: 'D1', severity: 'warning',
        title: `${older} are ${Math.round(gap)} months older than ${older === 'Prices' ? 'freight' : 'prices'}`,
        detail: `Prices (data through ${fmtDay(prices.dataThrough)}) vs freight (${fmtDay(freight.dataThrough)}). Threshold: ${ctx.params.freshnessMonths} months.`,
        action: { label: 'Open Uploads', kind: 'open-uploads' },
      })
    }
  }
  const latestUpload = [...ctx.uploads].sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt))[0]
  if (latestUpload && (new Date(TODAY).getTime() - new Date(latestUpload.uploadedAt).getTime()) / 864e5 > ctx.params.staleDays) {
    flags.push({ id: 'D2', code: 'D2', severity: 'info', title: 'Latest upload is older than ' + ctx.params.staleDays + ' days', action: { label: 'Open Uploads', kind: 'open-uploads' } })
  }

  if (prod.family === 'phosfusion' && prod.yieldGain != null && input.methods.includes('value')) {
    flags.push({ id: 'U1', code: 'U1', severity: r.U1 ? 'resolved' : 'warning', title: r.U1 ? 'Yield gain confirmed as t/ha' : 'Yield impact labelled “%” but used as t/ha', detail: r.U1 ? undefined : `The workbook labels the input “%” but divides ${input.yieldGain} by the application rate (t/ha). Confirm the unit.`, action: { label: 'Confirm unit', kind: 'open-input', target: 'yieldGain' } })
  }

  if (input.carbonPrice === 0) {
    flags.push({ id: 'C1', code: 'C1', severity: 'info', title: 'No carbon price set — carbon effect excluded', action: { label: 'Add a carbon price', kind: 'open-input', target: 'carbonPrice' } })
  }
  if (prod.pcfPlaceholder) {
    flags.push({ id: 'C2', code: 'C2', severity: r.C2 ? 'resolved' : 'warning', title: r.C2 ? 'Carbon footprint accepted as placeholder' : `Product carbon footprint ${input.pcfNew} t CO₂/t is a placeholder`, detail: r.C2 ? undefined : 'The workbook marks it “dummy”. Value pricing is unaffected until a carbon price is set.', action: { label: 'Open product', kind: 'open-product', target: prod.id } })
  }
  if (input.methods.includes('market') && input.benchmark == null) {
    flags.push({ id: 'M1', code: 'M1', severity: 'info', title: 'Market pricing needs a competitor benchmark', action: { label: 'Add benchmark', kind: 'add-benchmark' } })
  }
  flags.push({ id: 'A1', code: 'A1', severity: r.A1 ? 'resolved' : 'info', title: `Agent assumption: market share ${Math.round(input.marketShare * 1000) / 10}%`, detail: 'Used for volume and total margin.', action: { label: 'Edit', kind: 'open-input', target: 'marketShare' } })
  if (argus && snap.id === 'today' && input.referenceId === 'TSP' && input.priceType === 'high') {
    flags.push({ id: 'Q1', code: 'Q1', severity: 'info', title: 'TSP FOB quote: low 710 > high 691 — check the Argus file' })
  }

  const order = { error: 0, warning: 1, info: 2, resolved: 3 } as const
  return flags.sort((a, b) => order[a.severity] - order[b.severity])
}

export function fmtDay(iso: string) {
  const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${String(d).padStart(2, '0')} ${M[m - 1]} ${y}`
}

export function runEngine(input: RunInput, ctx: Ctx): RunOutput {
  const perProduct: Record<string, ProductResult> = {}
  for (const id of input.productIds) perProduct[id] = runProduct(input, ctx, id)
  return { perProduct, flags: computeFlags(input, ctx, perProduct) }
}

export function diffInputs(a: RunInput, b: RunInput): { key: keyof RunInput; before: unknown; after: unknown }[] {
  const out: { key: keyof RunInput; before: unknown; after: unknown }[] = []
  for (const k of Object.keys(b) as (keyof RunInput)[]) {
    if (k === 'comment' || k === 'resolved') continue
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) out.push({ key: k, before: a[k], after: b[k] })
  }
  return out
}
