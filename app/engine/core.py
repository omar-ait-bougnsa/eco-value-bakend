"""Orchestration entry point for the pure calculation engine."""
from typing import Optional
from .cost import calc_raw_material_cost, calc_raw_material_lines, calc_unit_costs
from .flags import compute_engine_flags, generate_audit_notes
from .margin import (
    calc_carbon_scenarios,
    calc_cgm,
    calc_nutrient_cgms,
    calc_ramp,
    calc_ref_cgm,
    calc_total_margin,
    calc_waterfall,
)
from .methods import calc_cost_plus, calc_market_pricing, calc_ref_minus, calc_value_pricing
from .types import (
    EngineInput,
    EngineOutput,
    Method,
    MethodResult,
    ProductResult,
    TraceEntry,
)

METHOD_LABELS = {
    'costPlus': 'Cost-plus',
    'market': 'Market pricing',
    'value': 'Value pricing',
    'refMinus': 'Reference minus',
}


def evaluate_product(
    input: EngineInput,
    prod_id: str,
) -> ProductResult:
    """Evaluate a single product against the reference product."""
    p = input.products[prod_id]
    ref = input.products[input.reference_id]

    # 1. Costing for new product
    lines = calc_raw_material_lines(p.recipe, input.cost_prices)
    raw_material = calc_raw_material_cost(lines)
    dna_override = p.dna_override or input.params.dna_per_ton
    dna, marketing, base_cost, unit_cost = calc_unit_costs(
        raw_material=raw_material,
        dna_per_ton=dna_override,
        include_dna=input.params.include_dna,
        marketing_pct=input.params.marketing_pct,
    )

    # 2. Costing for reference product
    ref_lines = calc_raw_material_lines(ref.recipe, input.cost_prices)
    ref_raw = calc_raw_material_cost(ref_lines)
    ref_dna_override = ref.dna_override or input.params.dna_per_ton
    ref_dna = ref_dna_override if input.params.include_dna else 0.0
    ref_base_cost = ref_raw + ref_dna
    ref_marketing = input.params.marketing_pct * ref_base_cost

    # 3. Four pricing methods
    # Cost-plus
    cost_plus = calc_cost_plus(unit_cost, input.params.cost_plus_margin)

    # Reference-minus (nutrients valued by nutrient_prices or cost_prices)
    nut_prices = input.nutrient_prices or input.cost_prices
    p2o5_val_ref, ref_minus = calc_ref_minus(
        ref_price=input.reference_price,
        ref_comp=ref.composition,
        new_comp=p.composition,
        nutrient_prices=nut_prices,
        n_per_nh3=input.params.nutrient_factors.n_per_nh3,
        k2o_per_kcl=input.params.nutrient_factors.k2o_per_kcl,
    )

    # Value pricing
    pcf_ref = ref.pcf if ref.pcf is not None else 0.7
    pcf_new = p.pcf if p.pcf is not None else 0.5
    agronomy = input.agronomy.get(prod_id)
    added_value, carbon_saving_per_t, carbon_effect, value_price = calc_value_pricing(
        ref_price=input.reference_price,
        agronomy=agronomy,
        pcf_ref=pcf_ref,
        pcf_new=pcf_new,
        carbon_price=input.params.carbon_price,
        value_share=input.params.value_share,
        mode=input.mode,
    )

    # Market pricing
    market_price = calc_market_pricing(input.benchmark_price)

    prices: dict[Method, Optional[float]] = {
        'costPlus': cost_plus,
        'market': market_price,
        'value': value_price,
        'refMinus': ref_minus,
    }

    # 4. Corridor bounds & Anchor price
    chosen_anchor = prices.get(input.params.anchor_method)
    anchor_price = chosen_anchor if chosen_anchor is not None else (ref_minus if ref_minus is not None else cost_plus)
    floor = cost_plus
    ceiling = value_price if value_price is not None else cost_plus

    # 5. Margins
    cgm = calc_cgm(anchor_price, unit_cost, marketing, input.mode)
    cgm_ref = calc_ref_cgm(
        ref_price=input.reference_price,
        ref_base_cost=ref_base_cost,
        ref_marketing=ref_marketing,
        include_ref_marketing=input.params.include_ref_marketing,
    )
    cgm_p2o5, cgm_s = calc_nutrient_cgms(cgm, p.composition.P2O5, p.recipe.get('sulphur', 0.0))
    total_margin = calc_total_margin(cgm, input.volume)

    # Method results list
    methods: list[MethodResult] = []
    for m in ('costPlus', 'refMinus', 'value', 'market'):
        if m in input.methods:
            m_price = prices[m]
            m_cgm = calc_cgm(m_price, unit_cost, marketing, input.mode)
            methods.append(MethodResult(
                method=m,
                label=METHOD_LABELS[m],
                price=m_price,
                cgm=m_cgm,
                cgmP2O5=(m_cgm / p.composition.P2O5) if (m_cgm is not None and p.composition.P2O5 > 0) else None,
                totalMargin=calc_total_margin(m_cgm, input.volume),
                deltaVsRef=(m_cgm - cgm_ref) if (m_cgm is not None and cgm_ref is not None) else None,
            ))

    # Waterfall
    waterfall = calc_waterfall(
        ref_name=ref.name,
        cgm_ref=cgm_ref,
        anchor_price=anchor_price,
        ref_price=input.reference_price,
        ref_cost=ref_base_cost,
        cost_for_margin=base_cost,
        cgm=cgm,
    )

    # Ramp & Carbon scenarios
    ramp = calc_ramp(input.volume)
    carbon_scenarios = calc_carbon_scenarios(carbon_saving_per_t)

    return ProductResult(
        productId=prod_id,
        name=p.name,
        lines=lines,
        rawMaterial=raw_material,
        dna=dna,
        marketing=marketing,
        unitCost=unit_cost,
        refPrice=input.reference_price,
        refCost=ref_base_cost,
        p2o5ValueRef=p2o5_val_ref,
        addedValue=added_value,
        carbonSavingPerT=carbon_saving_per_t,
        carbonEffect=carbon_effect,
        prices=prices,
        anchorPrice=anchor_price,
        floor=floor,
        ceiling=ceiling,
        cgm=cgm,
        cgmRef=cgm_ref,
        cgmP2O5=cgm_p2o5,
        cgmS=cgm_s,
        volume=input.volume,
        totalMargin=total_margin,
        methods=methods,
        waterfall=waterfall,
        ramp=ramp,
        carbonScenarios=carbon_scenarios,
    )


def evaluate(input: EngineInput) -> EngineOutput:
    """Evaluate full engine calculation for all specified products."""
    per_product = {
        pid: evaluate_product(input, pid)
        for pid in input.product_ids
    }
    flags = compute_engine_flags(input, per_product)
    notes = generate_audit_notes(input, per_product)

    # Basic trace entries for audit trail
    lead_id = input.product_ids[0]
    lead_res = per_product[lead_id]
    trace = [
        TraceEntry(key='unitCost', formula='Raw Material + D&A + Marketing', value=lead_res.unit_cost),
        TraceEntry(key='anchorPrice', formula=f'Anchor method: {input.params.anchor_method}', value=lead_res.anchor_price),
        TraceEntry(key='cgm', formula='Price - Total Cost (corrected)', value=lead_res.cgm),
    ]

    return EngineOutput(
        perProduct=per_product,
        flags=flags,
        notes=notes,
        trace=trace,
    )

