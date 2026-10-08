"""Pricing engine: pure functions, no I/O. Port of `src/engine/run.ts`."""
import math
import re
from dataclasses import dataclass
from datetime import date

from ..data.seed import DECK_TSP_COST, INGREDIENTS, TODAY
from ..schemas import (
    CarbonScenario, CostLine, Flag, FlagAction, InputChange, MethodResult, Parameters, Product, ProductResult,
    RampPoint, RunInput, RunOutput, Snapshot, UploadRecord, WaterfallStep,
)
from .period import CURRENT_YEAR, Span, blend_snapshot, fmt_day, touches_current_year


@dataclass
class Ctx:
    products: list[Product]
    snapshots: list[Snapshot]
    uploads: list[UploadRecord]
    params: Parameters


class UnknownProduct(LookupError):
    pass


METHOD_LABEL = {
    'costPlus': 'Cost-plus',
    'market': 'Market pricing',
    'value': 'Value pricing',
    'refMinus': 'Reference minus',
}
INGREDIENT_LABEL = {i.id: i.label for i in INGREDIENTS}
N_PER_AMMONIA = 0.82  # t N / t NH3 (matches workbook DAP column)
K2O_PER_KCL = 0.6
CARBON_SCENARIOS = [
    ('vol-low', 'Voluntary · low', 15),
    ('vol-high', 'Voluntary · high', 40),
    ('cbam', 'CBAM / EU-ETS ref.', 75),
]


def get_product(ctx: Ctx, id: str) -> Product:
    for p in ctx.products:
        if p.id == id:
            return p
    raise UnknownProduct(f'Unknown product {id}')


def resolve_snapshot(ctx: Ctx, period_from: date, period_to: date) -> Snapshot:
    """The market data for a run: a day-weighted blend of the yearly snapshots inside its analysis period."""
    return blend_snapshot(ctx.snapshots, Span(period_from, period_to))


def cost_lines(recipe: dict[str, float], s: Snapshot) -> list[CostLine]:
    out = []
    for id, qty in recipe.items():
        if qty > 0:
            price = s.inputs.get(id, 0)
            out.append(CostLine(id=id, label=INGREDIENT_LABEL.get(id, id), qty=qty, price=price, usd=qty * price))
    return out


def ref_price_for(s: Snapshot, ref: str, type: str) -> float | None:
    q = s.refPrices.get(ref)
    if q is None:
        return None
    return (q.high if q.high is not None else q.low) if type == 'high' else q.low


def months_between(a: date, b: date) -> float:
    return abs((a - b).days) / 30.4375


def run_product(input: RunInput, ctx: Ctx, product_id: str) -> ProductResult:
    p = get_product(ctx, product_id)
    ref = get_product(ctx, input.referenceId)
    snap = resolve_snapshot(ctx, input.periodFrom, input.periodTo)

    lines = cost_lines(p.recipe, snap)
    raw_material = sum(l.usd for l in lines)
    dna = input.dnaPerTon if input.fullCost else 0
    marketing = input.marketingPct * (raw_material + dna)
    cost_for_margin = raw_material + dna
    unit_cost = cost_for_margin + marketing

    ref_price = ref_price_for(snap, input.referenceId, input.priceType)
    ref_raw = sum(l.usd for l in cost_lines(ref.recipe, snap)) + dna
    ref_cost = input.refCostOverride if input.refCostOverride is not None and snap.id == 'today' else ref_raw

    # nutrient unit values (USD / t nutrient)
    v_n = snap.inputs['ammonia'] / N_PER_AMMONIA
    v_k = snap.inputs['kcl'] / K2O_PER_KCL
    v_s = snap.inputs['sulphur']
    rc, nc = ref.composition, p.composition

    p2o5_value_ref = ref_minus = None
    if ref_price is not None and rc.P2O5 > 0:
        pure_p = ref_price - rc.N * v_n - rc.K2O * v_k - rc.S * v_s
        p2o5_value_ref = pure_p / rc.P2O5
        ref_minus = nc.P2O5 * p2o5_value_ref + nc.N * v_n + nc.K2O * v_k + nc.S * v_s

    added_crop = input.yieldGain / input.appRateNew if input.appRateNew > 0 else 0
    added_value = added_crop * input.cropPrice
    carbon_saving_per_ha = input.pcfRef * input.appRateRef - input.pcfNew * input.appRateNew
    carbon_saving_per_t = carbon_saving_per_ha / input.appRateNew if input.appRateNew > 0 else 0
    carbon_effect = carbon_saving_per_t * input.carbonPrice
    value = added_value * input.valueShare + carbon_effect + ref_price if ref_price is not None else None
    cost_plus = unit_cost * (1 + input.costPlusMargin)

    prices = {'costPlus': cost_plus, 'market': input.benchmark, 'value': value, 'refMinus': ref_minus}
    anchor_price = next((x for x in (prices[input.anchor], ref_minus) if x is not None), cost_plus)
    floor = cost_plus
    ceiling = value if value is not None else cost_plus

    cgm_of = lambda price: None if price is None else price - unit_cost + marketing
    cgm_ref = ref_price - ref_cost if ref_price is not None else None
    volume = input.addressable * input.marketShare
    cgm = cgm_of(anchor_price)

    methods = []
    for m in ('costPlus', 'refMinus', 'value', 'market'):
        if m not in input.methods:
            continue
        c = cgm_of(prices[m])
        methods.append(MethodResult(
            method=m, label=METHOD_LABEL[m], price=prices[m], cgm=c,
            cgmP2O5=c / nc.P2O5 if c is not None and nc.P2O5 > 0 else None,
            totalMargin=c * volume if c is not None else None,
            deltaVsRef=c - cgm_ref if c is not None and cgm_ref is not None else None,
        ))

    waterfall = []
    if cgm_ref is not None and anchor_price is not None and ref_price is not None and cgm is not None:
        d_price = anchor_price - ref_price
        d_cost = ref_cost - cost_for_margin
        waterfall = [
            WaterfallStep(label=f'{ref.name} CGM', from_=0, to=cgm_ref, value=cgm_ref, kind='total'),
            WaterfallStep(label=f'Price vs {ref.name}', from_=cgm_ref, to=cgm_ref + d_price, value=d_price, kind='delta'),
            WaterfallStep(label='Raw-material savings', from_=cgm_ref + d_price, to=cgm_ref + d_price + d_cost, value=d_cost, kind='delta'),
            WaterfallStep(label='New product CGM', from_=0, to=cgm, value=cgm, kind='total'),
        ]

    ramp = []
    for year in range(CURRENT_YEAR, CURRENT_YEAR + 10):
        t = min(max((year - CURRENT_YEAR) / max(input.rampTargetYear - CURRENT_YEAR, 1), 0), 1)
        ramp.append(RampPoint(year=year, kt=volume * t / 1000))

    sulphur = p.recipe.get('sulphur', 0)
    return ProductResult(
        productId=product_id, name=p.name, lines=lines, rawMaterial=raw_material, dna=dna, marketing=marketing,
        unitCost=unit_cost, refPrice=ref_price, refCost=ref_cost, p2o5ValueRef=p2o5_value_ref,
        addedValue=added_value, carbonSavingPerT=carbon_saving_per_t, carbonEffect=carbon_effect,
        prices=prices, anchorPrice=anchor_price, floor=floor, ceiling=ceiling,
        cgm=cgm, cgmRef=cgm_ref,
        cgmP2O5=cgm / nc.P2O5 if cgm is not None and nc.P2O5 > 0 else None,
        cgmS=cgm / sulphur if cgm is not None and sulphur > 0 else None,
        volume=volume, totalMargin=cgm * volume if cgm is not None else None,
        methods=methods, waterfall=waterfall, ramp=ramp,
        carbonScenarios=[CarbonScenario(id=i, label=l, price=pr, delta=carbon_saving_per_t * pr) for i, l, pr in CARBON_SCENARIOS],
    )


def _f2(n: float) -> str:
    return f'{n:,.2f}'


def _num(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else repr(float(n))


def _latest(uploads: list[UploadRecord], key=lambda u: u.dataThrough) -> UploadRecord | None:
    return max(uploads, key=key, default=None)


def _argus(uploads: list[UploadRecord]) -> UploadRecord | None:
    return _latest([u for u in uploads if u.type == 'prices' and re.search('argus', u.name, re.I)])


def freshness_flags(uploads: list[UploadRecord], params: Parameters, period: Span) -> list[Flag]:
    """D1: prices and freight are too far apart. D2: nothing has been uploaded for a while."""
    flags: list[Flag] = []
    prices = _argus(uploads) or _latest([u for u in uploads if u.type == 'prices'])
    freight = _latest([u for u in uploads if u.type == 'freight'])
    if prices and freight and touches_current_year(period):
        gap = months_between(prices.dataThrough, freight.dataThrough)
        if gap >= params.freshnessMonths:
            older, newer = ('Prices', 'freight') if prices.dataThrough < freight.dataThrough else ('Freight', 'prices')
            flags.append(Flag(
                id='D1', code='D1', severity='warning',
                title=f'{older} are {math.floor(gap + 0.5)} months older than {newer}',
                detail=f'Prices (data through {fmt_day(prices.dataThrough)}) vs freight ({fmt_day(freight.dataThrough)}). Threshold: {_num(params.freshnessMonths)} months.',
                action=FlagAction(label='Open Uploads', kind='open-uploads'),
            ))
    latest_upload = _latest(uploads, key=lambda u: u.uploadedAt)
    if latest_upload and (TODAY - latest_upload.uploadedAt).days > params.staleDays:
        flags.append(Flag(id='D2', code='D2', severity='info', title=f'Latest upload is older than {params.staleDays} days',
                          action=FlagAction(label='Open Uploads', kind='open-uploads')))
    return flags


def compute_flags(input: RunInput, ctx: Ctx, per_product: dict[str, ProductResult]) -> list[Flag]:
    flags: list[Flag] = []
    r = input.resolved
    snap = resolve_snapshot(ctx, input.periodFrom, input.periodTo)
    lead = per_product[input.productIds[0]]
    prod = get_product(ctx, input.productIds[0])

    if lead.refPrice is None:
        flags.append(Flag(id='N1', code='N1', severity='error', title=f'No {input.referenceId} price for {snap.label}',
                          detail='Pick another reference (DAP, MAP or TSP) or another snapshot.'))

    if input.referenceId == 'TSP' and snap.id == 'today':
        if r.get('S1'):
            flags.append(Flag(id='S1', code='S1', severity='resolved', title=f'TSP full cost set to {_f2(lead.refCost or 0)} USD/t',
                              detail='You chose the business-case deck figure.' if r['S1'] == 'deck' else 'You chose the Standard cost 2026 figure.'))
        else:
            flags.append(Flag(id='S1', code='S1', severity='warning', title='TSP full production cost differs between sources',
                              detail=f'Business-case deck {DECK_TSP_COST} USD/t vs Standard cost 2026 {_f2(lead.refCost or 0)} USD/t.',
                              action=FlagAction(label='Answer', kind='answer')))

    below = next((x for x in per_product.values() if x.anchorPrice is not None and x.anchorPrice < x.floor), None)
    if below:
        flags.append(Flag(
            id='P1', code='P1', severity='resolved' if r.get('P1') else 'warning',
            title=f'Anchor is below the cost-plus floor ({_f2(below.anchorPrice)} < {_f2(below.floor)})',
            detail='At this price the margin over cost is thin. Switch the anchor or raise the margin.',
            action=FlagAction(label='Review', kind='review', target='pricing'),
        ))

    flags += freshness_flags(ctx.uploads, ctx.params, Span(input.periodFrom, input.periodTo))
    argus = _argus(ctx.uploads)

    if prod.family == 'phosfusion' and prod.yieldGain is not None and 'value' in input.methods:
        done = bool(r.get('U1'))
        flags.append(Flag(
            id='U1', code='U1', severity='resolved' if done else 'warning',
            title='Yield gain confirmed as t/ha' if done else 'Yield impact labelled “%” but used as t/ha',
            detail=None if done else f'The workbook labels the input “%” but divides {_num(input.yieldGain)} by the application rate (t/ha). Confirm the unit.',
            action=FlagAction(label='Confirm unit', kind='open-input', target='yieldGain'),
        ))

    if input.carbonPrice == 0:
        flags.append(Flag(id='C1', code='C1', severity='info', title='No carbon price set — carbon effect excluded',
                          action=FlagAction(label='Add a carbon price', kind='open-input', target='carbonPrice')))
    if prod.pcfPlaceholder:
        done = bool(r.get('C2'))
        flags.append(Flag(
            id='C2', code='C2', severity='resolved' if done else 'warning',
            title='Carbon footprint accepted as placeholder' if done else f'Product carbon footprint {_num(input.pcfNew)} t CO₂/t is a placeholder',
            detail=None if done else 'The workbook marks it “dummy”. Value pricing is unaffected until a carbon price is set.',
            action=FlagAction(label='Open product', kind='open-product', target=prod.id),
        ))
    if 'market' in input.methods and input.benchmark is None:
        flags.append(Flag(id='M1', code='M1', severity='info', title='Market pricing needs a competitor benchmark',
                          action=FlagAction(label='Add benchmark', kind='add-benchmark')))
    flags.append(Flag(
        id='A1', code='A1', severity='resolved' if r.get('A1') else 'info',
        title=f'Agent assumption: market share {_num(math.floor(input.marketShare * 1000 + 0.5) / 10)}%',
        detail='Used for volume and total margin.',
        action=FlagAction(label='Edit', kind='open-input', target='marketShare'),
    ))
    if argus and snap.id == 'today' and input.referenceId == 'TSP' and input.priceType == 'high':
        flags.append(Flag(id='Q1', code='Q1', severity='info', title='TSP FOB quote: low 710 > high 691 — check the Argus file'))

    order = {'error': 0, 'warning': 1, 'info': 2, 'resolved': 3}
    return sorted(flags, key=lambda f: order[f.severity])


def run_engine(input: RunInput, ctx: Ctx) -> RunOutput:
    per_product = {id: run_product(input, ctx, id) for id in input.productIds}
    return RunOutput(perProduct=per_product, flags=compute_flags(input, ctx, per_product))


def diff_inputs(a: RunInput, b: RunInput) -> list[InputChange]:
    x, y = a.model_dump(mode='json'), b.model_dump(mode='json')
    return [InputChange(key=k, before=x[k], after=y[k]) for k in y if k not in ('comment', 'resolved') and x[k] != y[k]]
