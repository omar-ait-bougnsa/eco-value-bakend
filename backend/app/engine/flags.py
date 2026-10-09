"""Rule-based flag and audit note generators."""
from typing import Optional
from .types import EngineInput, Flag, FlagAction, Note, ProductDef, ProductResult


def compute_engine_flags(
    input: EngineInput,
    per_product: dict[str, ProductResult],
) -> list[Flag]:
    """Evaluate pure mathematical and data consistency flags."""
    flags: list[Flag] = []

    # P1: Anchor below cost-plus floor
    below = next((r for r in per_product.values() if r.anchor_price is not None and r.anchor_price < r.floor), None)
    if below:
        flags.append(Flag(
            id='P1',
            code='P1',
            severity='warning',
            title=f'Anchor is below the cost-plus floor ({below.anchor_price:,.2f} < {below.floor:,.2f})',
            detail='At this price the margin over cost is thin. Switch the anchor or raise the margin.',
            action=FlagAction(label='Review', kind='review', target='pricing'),
        ))

    # Check lead product
    lead_id = input.product_ids[0]
    lead_prod = input.products.get(lead_id)
    lead_res = per_product.get(lead_id)

    # W1: Yield gain unit open item
    lead_agro = input.agronomy.get(lead_id)
    if lead_prod and lead_prod.family == 'phosfusion' and lead_agro and 'value' in input.methods:
        flags.append(Flag(
            id='W1',
            code='W1',
            severity='warning',
            title='Yield impact labelled “%” but used as t/ha',
            detail=f'The workbook labels the input “%” but divides {lead_agro.yield_gain} by the application rate (t/ha). Confirm the unit.',
            action=FlagAction(label='Confirm unit', kind='open-input', target='yieldGain'),
        ))

    # W2: Sulphur price budget note
    sulphur_price = input.cost_prices.get('sulphur', 0.0)
    if sulphur_price >= 800:
        flags.append(Flag(
            id='W2',
            code='W2',
            severity='info',
            title=f'Elevated sulphur price ({sulphur_price:,.0f} USD/t) drives unit cost and margin',
            detail='Budget 2026 sulphur is 900 USD/t vs 285 USD/t in 2027. Review later years under Conditions.',
            action=FlagAction(label='View 2027', kind='open-conditions', target='2027'),
        ))

    # M1: Market pricing without competitor benchmark
    if 'market' in input.methods and input.benchmark_price is None:
        flags.append(Flag(
            id='M1',
            code='M1',
            severity='info',
            title='Market pricing needs a competitor benchmark',
            detail='Market pricing is active but no benchmark price was provided.',
            action=FlagAction(label='Add benchmark', kind='add-benchmark'),
        ))

    # M2: Marketing applied to new product only
    if input.params.marketing_pct > 0 and not input.params.include_ref_marketing:
        flags.append(Flag(
            id='M2',
            code='M2',
            severity='info',
            title=f'Marketing ({input.params.marketing_pct * 100:.0f}%) applied to new product only',
            detail=f'The reference product ({input.reference_id}) bears no marketing expense, matching legacy workbook behavior.',
            action=FlagAction(label='Review marketing', kind='open-input', target='marketingPct'),
        ))

    # C1: No carbon price set
    if input.params.carbon_price == 0:
        flags.append(Flag(
            id='C1',
            code='C1',
            severity='info',
            title='No carbon price set — carbon effect excluded',
            detail='Carbon price is 0 USD/t CO₂. Value pricing excludes carbon premium until a price is set.',
            action=FlagAction(label='Add carbon price', kind='open-input', target='carbonPrice'),
        ))

    # C2: Product carbon footprint is placeholder
    for pid in input.product_ids:
        prod = input.products.get(pid)
        if prod and prod.pcf_placeholder:
            flags.append(Flag(
                id=f'C2_{pid}',
                code='C2',
                severity='warning',
                title=f'Product carbon footprint {prod.pcf} t CO₂/t is a placeholder',
                detail=f'{prod.name} carbon footprint is marked dummy. Value pricing is unaffected until a carbon price is set.',
                action=FlagAction(label='Open product', kind='open-product', target=prod.id),
            ))

    # A2: Agronomic trial data is synthetic/placeholder
    for pid in input.product_ids:
        agro = input.agronomy.get(pid)
        if agro and agro.status == 'placeholder':
            flags.append(Flag(
                id=f'A2_{pid}',
                code='A2',
                severity='warning',
                title=f'Agronomic trial data for {pid} is synthetic/placeholder',
                detail='Yield gain and application rates are based on synthetic trial estimates.',
                action=FlagAction(label='View trials', kind='open-uploads'),
            ))

    # A3: No trial data available
    for pid in input.product_ids:
        if input.agronomy.get(pid) is None and 'value' in input.methods:
            flags.append(Flag(
                id=f'A3_{pid}',
                code='A3',
                severity='info',
                title=f'No trial data available for {pid} vs {input.reference_id}',
                detail='Value pricing requires agronomic trial inputs.',
                action=FlagAction(label='Add trial data', kind='open-uploads'),
            ))

    # V1: Total volume not provided
    if input.volume is None:
        flags.append(Flag(
            id='V1',
            code='V1',
            severity='info',
            title='Volume not provided — total annual margin bypassed',
            detail='Enter addressable volume to compute aggregate financial return.',
            action=FlagAction(label='Enter volume', kind='open-input', target='volume'),
        ))

    order = {'error': 0, 'warning': 1, 'info': 2, 'resolved': 3}
    return sorted(flags, key=lambda f: order.get(f.severity, 4))


def generate_audit_notes(
    input: EngineInput,
    per_product: dict[str, ProductResult],
) -> list[Note]:
    """Generate formula correction and audit notes (X1, X2, Nutrient Price Source)."""
    notes: list[Note] = []
    lead_id = input.product_ids[0]
    lead_res = per_product.get(lead_id)

    # Note X1: Carbon calculation
    if lead_res:
        notes.append(Note(
            code='X1',
            title='Carbon Effect Formula Correction',
            cell='B Case H48',
            workbookVal='+0.40 USD/t (at 40 USD/tCO₂)',
            engineVal=f'+{lead_res.carbon_effect:.2f} USD/t',
            impact='Converts carbon savings to per ton of product rather than per hectare.',
        ))

    # Note X2: Marketing in CGM
    if lead_res:
        notes.append(Note(
            code='X2',
            title='Marketing Cost in Contribution Gross Margin (CGM)',
            cell='B Case H92',
            workbookVal='+3.02 USD/t (at 10% marketing)',
            engineVal=f'{lead_res.cgm:.2f} USD/t',
            impact='Retains marketing as an operational expense instead of adding it back.',
        ))

    # Note on Nutrient valuation prices (Decision D-V1)
    if input.nutrient_prices:
        notes.append(Note(
            code='N_SRC',
            title='Nutrient Valuation Prices in Reference-Minus',
            cell='B Case H66:H80',
            workbookVal='Budget 2026 prices',
            engineVal='Selected nutrient price series',
            impact='Nutrients in reference-minus valued using dedicated market reference prices.',
        ))

    return notes

