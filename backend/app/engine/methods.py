"""The four pricing methods: Cost-Plus, Reference-Minus, Value Pricing, and Market Pricing."""
from typing import Optional
from .types import AgronomyData, Composition, Mode


def calc_cost_plus(total_unit_cost: float, margin: float) -> float:
    """Cost-plus pricing: Total Unit Cost * (1 + margin)."""
    return total_unit_cost * (1.0 + margin)


def calc_ref_minus(
    ref_price: Optional[float],
    ref_comp: Composition,
    new_comp: Composition,
    nutrient_prices: dict[str, float],
    n_per_nh3: float = 0.82,
    k2o_per_kcl: float = 0.60,
) -> tuple[Optional[float], Optional[float]]:
    """Reference-minus pricing.
    Deducts nutrient values of N, K2O, and S from the reference price to isolate pure P2O5 valuation,
    then adds nutrient values for the new product based on its composition fractions.
    Returns:
        (p2o5_value_ref, price_ref_minus)
    """
    if ref_price is None or ref_comp.P2O5 <= 0:
        return None, None

    v_n = nutrient_prices.get('ammonia', 0.0) / n_per_nh3 if n_per_nh3 > 0 else 0.0
    v_k = nutrient_prices.get('kcl', 0.0) / k2o_per_kcl if k2o_per_kcl > 0 else 0.0
    v_s = nutrient_prices.get('sulphur', 0.0)

    # Pure phosphate valuation in reference product
    pure_p = ref_price - (ref_comp.N * v_n + ref_comp.K2O * v_k + ref_comp.S * v_s)
    p2o5_value_ref = pure_p / ref_comp.P2O5

    # New product valuation
    price_ref_minus = (
        new_comp.P2O5 * p2o5_value_ref
        + new_comp.N * v_n
        + new_comp.K2O * v_k
        + new_comp.S * v_s
    )
    return p2o5_value_ref, price_ref_minus


def calc_value_pricing(
    ref_price: Optional[float],
    agronomy: Optional[AgronomyData],
    pcf_ref: float,
    pcf_new: float,
    carbon_price: float,
    value_share: float,
    mode: Mode = 'corrected',
) -> tuple[float, float, float, Optional[float]]:
    """Value pricing: Reference Price + (Agronomic Value Created * value_share) + Carbon Effect.
    Correction X1:
      mode="corrected": carbon effect per ton product = carbon_saving_per_ton * carbon_price
      mode="workbook": carbon effect per hectare = carbon_saving_per_ha * carbon_price
    Returns:
        (added_value, carbon_saving_per_ton, carbon_effect, price_value)
    """
    app_rate_new = agronomy.app_rate_new if agronomy else 0.0
    app_rate_ref = agronomy.app_rate_ref if agronomy else 0.0

    # Agronomic value created
    if agronomy and app_rate_new > 0:
        added_crop = agronomy.yield_gain / app_rate_new
        added_value = added_crop * agronomy.crop_price
    else:
        added_value = 0.0

    # Carbon differential
    if agronomy and app_rate_new > 0:
        carbon_saving_per_ha = (pcf_ref * app_rate_ref) - (pcf_new * app_rate_new)
        carbon_saving_per_ton = carbon_saving_per_ha / app_rate_new
    else:
        carbon_saving_per_ha = 0.0
        carbon_saving_per_ton = 0.0

    # Carbon effect with X1 handling
    if mode == 'corrected':
        carbon_effect = carbon_saving_per_ton * carbon_price
    else:
        carbon_effect = carbon_saving_per_ha * carbon_price

    if ref_price is not None:
        price_value = ref_price + (added_value * value_share) + carbon_effect
    else:
        price_value = None

    return added_value, carbon_saving_per_ton, carbon_effect, price_value


def calc_market_pricing(benchmark: Optional[float]) -> Optional[float]:
    """Market pricing: direct competitor benchmark price."""
    return benchmark

