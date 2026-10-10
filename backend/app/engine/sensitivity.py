"""Sulphur sensitivity analysis and exact analytical break-evens."""
from typing import Optional
from .types import BreakEven, Mode, ProductDef, SensitivityPoint, SensitivityResult


def run_sulphur_sensitivity(
    new_product: ProductDef,
    ref_product: ProductDef,
    cost_prices: dict[str, float],
    anchor_price: Optional[float],
    ref_price: Optional[float],
    dna_per_ton: float = 0.0,
    marketing_pct: float = 0.0,
    include_ref_marketing: bool = False,
    mode: Mode = 'corrected',
    from_price: float = 100.0,
    to_price: float = 1000.0,
    step: float = 50.0,
) -> SensitivityResult:
    """Evaluate CGM as a function of sulphur price over a parameter sweep,
    and compute exact linear zero-margin and crossover break-even points.
    """
    # Non-sulphur raw material cost per ton
    non_s_prices = {k: v for k, v in cost_prices.items() if k != 'sulphur'}
    c_non_s_new = sum(new_product.recipe.get(k, 0.0) * p for k, p in non_s_prices.items() if k != 'acp')
    c_non_s_ref = sum(ref_product.recipe.get(k, 0.0) * p for k, p in non_s_prices.items() if k != 'acp')

    s_recipe_new = new_product.recipe.get('sulphur', 0.0)
    s_recipe_ref = ref_product.recipe.get('sulphur', 0.0)

    # Base fixed costs (excluding sulphur)
    base_fixed_new = c_non_s_new + dna_per_ton
    base_fixed_ref = c_non_s_ref + dna_per_ton

    points: list[SensitivityPoint] = []
    curr_p = from_price
    while curr_p <= to_price + 1e-6:
        # Cost new
        raw_new = c_non_s_new + (s_recipe_new * curr_p)
        base_new = raw_new + dna_per_ton
        mkt_new = marketing_pct * base_new
        unit_new = base_new + mkt_new
        cgm_new = None
        if anchor_price is not None:
            cgm_new = (anchor_price - unit_new) if mode == 'corrected' else (anchor_price - unit_new + mkt_new)

        # Cost ref
        raw_ref = c_non_s_ref + (s_recipe_ref * curr_p)
        base_ref = raw_ref + dna_per_ton
        mkt_ref = (marketing_pct * base_ref) if include_ref_marketing else 0.0
        unit_ref = base_ref + mkt_ref
        cgm_ref = (ref_price - unit_ref) if ref_price is not None else None

        delta_cgm = (cgm_new - cgm_ref) if (cgm_new is not None and cgm_ref is not None) else None

        points.append(SensitivityPoint(
            sulphur_price=round(curr_p, 2),
            cgm_new=cgm_new,
            cgm_ref=cgm_ref,
            delta_cgm=delta_cgm,
        ))
        curr_p += step

    # Analytical break-evens
    break_evens: list[BreakEven] = []

    # 1. Zero-margin break-even for new product (CGM_new = 0)
    if anchor_price is not None and s_recipe_new > 0:
        if mode == 'corrected':
            # Price - (base_fixed + s_qty * P_S) * (1 + mkt) = 0
            p_s_zero_new = ((anchor_price / (1.0 + marketing_pct)) - base_fixed_new) / s_recipe_new
        else:
            # Price - (base_fixed + s_qty * P_S) = 0
            p_s_zero_new = (anchor_price - base_fixed_new) / s_recipe_new

        break_evens.append(BreakEven(
            product_id=new_product.id,
            sulphur_price=round(p_s_zero_new, 2),
            kind='zero_margin',
            note=f'{new_product.name} zero-margin sulphur break-even',
        ))

    # 2. Zero-margin break-even for reference product (CGM_ref = 0)
    if ref_price is not None and s_recipe_ref > 0:
        mkt_rate = marketing_pct if include_ref_marketing else 0.0
        p_s_zero_ref = ((ref_price / (1.0 + mkt_rate)) - base_fixed_ref) / s_recipe_ref
        break_evens.append(BreakEven(
            product_id=ref_product.id,
            sulphur_price=round(p_s_zero_ref, 2),
            kind='zero_margin',
            note=f'{ref_product.name} zero-margin sulphur break-even',
        ))

    # 3. Parity crossover break-even (CGM_new == CGM_ref)
    # CGM = price − rate × (fixed + s × P_S), with rate = 1 + marketing where marketing is a cost of that product.
    # Equal margins: P_S × (rate_ref × s_ref − rate_new × s_new) = (price_ref − rate_ref × fixed_ref) − (price_new − rate_new × fixed_new)
    rate_new = 1.0 + marketing_pct if mode == 'corrected' else 1.0
    rate_ref = 1.0 + marketing_pct if include_ref_marketing else 1.0
    ds = rate_ref * s_recipe_ref - rate_new * s_recipe_new
    if anchor_price is not None and ref_price is not None and abs(ds) > 1e-6:
        p_s_crossover = ((ref_price - rate_ref * base_fixed_ref) - (anchor_price - rate_new * base_fixed_new)) / ds
        break_evens.append(BreakEven(
            product_id=new_product.id,
            sulphur_price=round(p_s_crossover, 2),
            kind='crossover',
            note=f'Parity crossover sulphur price between {new_product.name} and {ref_product.name}',
        ))

    return SensitivityResult(points=points, break_evens=break_evens)

