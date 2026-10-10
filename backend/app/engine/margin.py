"""Contribution gross margins, nutrient-normalized margins, waterfalls, and ramp projections."""
from typing import Optional
from .types import CarbonScenario, Mode, RampPoint, WaterfallStep

DEFAULT_CARBON_SCENARIOS = [
    ('vol-low', 'Voluntary · low', 15.0),
    ('vol-high', 'Voluntary · high', 40.0),
    ('cbam', 'CBAM / EU-ETS ref.', 75.0),
]


def calc_cgm(
    price: Optional[float],
    total_unit_cost: float,
    marketing: float,
    mode: Mode = 'corrected',
) -> Optional[float]:
    """Calculate Contribution Gross Margin (CGM) of product.
    Correction X2:
      mode="corrected": CGM = price - total_unit_cost (marketing retained as cost).
      mode="workbook": CGM = price - total_unit_cost + marketing (legacy bug cancels marketing).
    """
    if price is None:
        return None
    if mode == 'corrected':
        return price - total_unit_cost
    else:
        return price - total_unit_cost + marketing


def calc_ref_cgm(
    ref_price: Optional[float],
    ref_base_cost: float,
    ref_marketing: float = 0.0,
    include_ref_marketing: bool = False,
) -> Optional[float]:
    """Calculate Reference product CGM.
    Workbook behavior (Decision R2): Reference bears no marketing by default.
    """
    if ref_price is None:
        return None
    deduction = ref_marketing if include_ref_marketing else 0.0
    return ref_price - ref_base_cost - deduction


def calc_nutrient_cgms(
    cgm: Optional[float],
    p2o5_fraction: float,
    sulphur_recipe: float,
) -> tuple[Optional[float], Optional[float]]:
    """Calculate normalized margins:
    - CGM per ton P2O5 = CGM / P2O5 composition fraction
    - CGM per ton Sulphur = CGM / Sulphur consumption in recipe
    """
    cgm_p2o5 = (cgm / p2o5_fraction) if (cgm is not None and p2o5_fraction > 0) else None
    cgm_s = (cgm / sulphur_recipe) if (cgm is not None and sulphur_recipe > 0) else None
    return cgm_p2o5, cgm_s


def calc_total_margin(cgm: Optional[float], volume: Optional[float]) -> Optional[float]:
    """Annual total gross margin: CGM * volume."""
    if cgm is not None and volume is not None:
        return cgm * volume
    return None


def calc_waterfall(
    ref_name: str,
    cgm_ref: Optional[float],
    anchor_price: Optional[float],
    ref_price: Optional[float],
    ref_cost: Optional[float],
    cost_for_margin: float,
    cgm: Optional[float],
) -> list[WaterfallStep]:
    """Build the 4-step margin bridge waterfall."""
    if cgm_ref is None or anchor_price is None or ref_price is None or ref_cost is None or cgm is None:
        return []

    d_price = anchor_price - ref_price
    d_cost = ref_cost - cost_for_margin
    return [
        WaterfallStep(label=f'{ref_name} CGM', from_=0.0, to=cgm_ref, value=cgm_ref, kind='total'),
        WaterfallStep(label=f'Price vs {ref_name}', from_=cgm_ref, to=cgm_ref + d_price, value=d_price, kind='delta'),
        WaterfallStep(label='Cost savings', from_=cgm_ref + d_price, to=cgm_ref + d_price + d_cost, value=d_cost, kind='delta'),
        WaterfallStep(label='New product CGM', from_=0.0, to=cgm, value=cgm, kind='total'),
    ]


def calc_ramp(
    volume: Optional[float],
    current_year: int = 2026,
    ramp_target_year: int = 2030,
) -> list[RampPoint]:
    """10-year volume ramp projection."""
    vol = volume if volume is not None else 0.0
    ramp: list[RampPoint] = []
    denom = max(ramp_target_year - current_year, 1)
    for year in range(current_year, current_year + 10):
        t = min(max((year - current_year) / denom, 0.0), 1.0)
        ramp.append(RampPoint(year=year, kt=vol * t / 1000.0))
    return ramp


def calc_carbon_scenarios(
    carbon_saving_per_ton: float,
    scenarios: Optional[list[tuple[str, str, float]]] = None,
) -> list[CarbonScenario]:
    """Calculate sensitivity across standard carbon price scenarios."""
    active = scenarios or DEFAULT_CARBON_SCENARIOS
    return [
        CarbonScenario(id=sid, label=lbl, price=pr, delta=carbon_saving_per_ton * pr)
        for sid, lbl, pr in active
    ]

