"""Business limits of the inputs: one place, used to validate API input and served to the forms (GET /api/limits).

The defaults are working assumptions, not confirmed business rules (see README.md, "Validation limits").
Change them without touching the code with `EVS_LIMITS`, a JSON object of the fields to override:

    EVS_LIMITS='{"recipeQtyMax": 2.5, "pcfMax": 5}'
"""
import json
import math
import os
import re
from functools import lru_cache
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Limits(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

    productNameMin: int = Field(3, ge=1, description='Characters in a product name, after trimming')
    productNameMax: int = Field(80, ge=1)
    recipeQtyMax: float = Field(3.0, gt=0, description='t of one ingredient per t of product')
    recipeTotalMax: float = Field(4.0, gt=0, description='t of all ingredients per t of product')
    nutrientTotalMax: float = Field(1.0, gt=0, le=1, description='N + P2O5 + K2O + S, as a fraction of the product')
    pcfMax: float = Field(10.0, gt=0, description='t CO2 per t of product')
    appRateMax: float = Field(5.0, gt=0, description='t of product per ha')
    yieldGainMaxTHa: float = Field(20.0, gt=0, description='Yield gain in t of crop per ha')
    yieldGainMaxPct: float = Field(100.0, gt=0, description='Yield gain in % of the baseline yield')
    baselineYieldMax: float = Field(100.0, gt=0, description='Yield of the crop without the product, t per ha')
    priceMax: float = Field(10_000.0, gt=0, description='USD per t: crop price, competitor benchmark, carbon price, reference cost, D&A')
    marginMax: float = Field(2.0, gt=0, description='Cost-plus margin as a fraction (2 = 200 %)')
    marketingMax: float = Field(1.0, gt=0, description='Marketing cost as a fraction of the cost')
    addressableMax: float = Field(1e9, gt=0, description='Addressable market, t per year')
    rampYearSpan: int = Field(30, ge=1, description='Years after the current one a ramp-up target can be set to')
    uploadMaxBytes: int = Field(20 * 1024 * 1024, gt=0)


@lru_cache
def get_limits() -> Limits:
    raw = os.getenv('EVS_LIMITS', '').strip()
    return Limits(**json.loads(raw)) if raw else Limits()


class FieldError(Exception):
    """One or more inputs out of bounds: (field, message) pairs, reported together as a 400."""

    def __init__(self, errors: list[tuple[str, str]]):
        super().__init__('; '.join(f'{f}: {m}' for f, m in errors))
        self.errors = errors


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _range(errors: list, field: str, v: Any, lo: float, hi: float, unit: str, *, optional: bool = False, above: bool = False) -> None:
    """`v` is a finite number in [lo, hi] (or (lo, hi] with `above`)."""
    if v is None:
        if not optional:
            errors.append((field, 'is required'))
        return
    if not _finite(v):
        errors.append((field, 'must be a finite number'))
    elif v > hi or v < lo or (above and v <= lo):
        errors.append((field, f'must be {"above" if above else "between"} {lo:g} {"and at most" if above else "and"} {hi:g} {unit}'.strip()))


def product_errors(p: dict[str, Any], limits: Optional[Limits] = None) -> list[tuple[str, str]]:
    """What is wrong with a product, field by field. Empty when it can be used in a run."""
    L, e = limits or get_limits(), []
    name = (p.get('name') or '').strip()
    if not L.productNameMin <= len(name) <= L.productNameMax:
        e.append(('name', f'must be {L.productNameMin} to {L.productNameMax} characters'))
    elif not re.search(r'[^\W\d_]', name):
        e.append(('name', 'must contain letters'))
    elif len(set(re.sub(r'\W', '', name.lower()))) < 2:
        e.append(('name', 'is not a name: one character repeated'))

    recipe = p.get('recipe') or {}
    for k, q in recipe.items():
        _range(e, f'recipe.{k}', q, 0, L.recipeQtyMax, 't/t')
    quantities = [q for q in recipe.values() if _finite(q)]
    if not any(q > 0 for q in quantities):
        e.append(('recipe', 'needs at least one ingredient with a quantity'))
    elif sum(quantities) > L.recipeTotalMax:
        e.append(('recipe', f'uses {sum(quantities):g} t of ingredients per t of product: at most {L.recipeTotalMax:g} t/t'))

    comp = p.get('composition') or {}
    for k in ('N', 'P2O5', 'K2O', 'S'):
        _range(e, f'composition.{k}', comp.get(k, 0), 0, 1, '(0–100 %)')
    total = sum(v for v in comp.values() if _finite(v))
    if total > L.nutrientTotalMax + 1e-9:
        e.append(('composition', f'nutrients add up to {total * 100:g} %: at most {L.nutrientTotalMax * 100:g} %'))

    _range(e, 'pcf', p.get('pcf'), 0, L.pcfMax, 't CO₂/t', optional=True)
    _range(e, 'appRate', p.get('appRate'), 0, L.appRateMax, 't/ha', optional=True, above=True)
    e += yield_errors(p.get('yieldGain'), p.get('yieldGainUnit'), p.get('baselineYield'), L, optional=True)
    return e


def yield_errors(gain: Any, unit: Optional[str], baseline: Any, L: Limits, *, optional: bool = False) -> list[tuple[str, str]]:
    """A yield gain is a quantity with a unit. In % it needs the yield it is a share of, to become t/ha."""
    e: list[tuple[str, str]] = []
    if unit == '%':
        _range(e, 'yieldGain', gain, 0, L.yieldGainMaxPct, '%', optional=optional)
        if gain is not None:
            _range(e, 'baselineYield', baseline, 0, L.baselineYieldMax, 't/ha', above=True)
            if baseline is None:
                e[-1] = ('baselineYield', 'is required to turn a yield gain in % into t/ha')
    else:
        _range(e, 'yieldGain', gain, 0, L.yieldGainMaxTHa, 't/ha', optional=optional)
        _range(e, 'baselineYield', baseline, 0, L.baselineYieldMax, 't/ha', optional=True, above=True)
    return e


def run_input_errors(i: dict[str, Any], current_year: int, limits: Optional[Limits] = None) -> list[tuple[str, str]]:
    """Bounds of a new run input. Saved runs are not checked again: they stay as they were made."""
    L, e = limits or get_limits(), []
    _range(e, 'costPlusMargin', i.get('costPlusMargin'), 0, L.marginMax, '(fraction)')
    _range(e, 'marketingPct', i.get('marketingPct'), 0, L.marketingMax, '(fraction)')
    for f in ('valueShare', 'marketShare'):
        _range(e, f, i.get(f), 0, 1, '(fraction)')
    for f in ('dnaPerTon', 'cropPrice', 'carbonPrice'):
        _range(e, f, i.get(f), 0, L.priceMax, 'USD/t')
    for f in ('benchmark', 'refCostOverride'):
        _range(e, f, i.get(f), 0, L.priceMax, 'USD/t', optional=True, above=True)
    for f in ('appRateNew', 'appRateRef'):
        _range(e, f, i.get(f), 0, L.appRateMax, 't/ha', above=True)
    for f in ('pcfNew', 'pcfRef'):
        _range(e, f, i.get(f), 0, L.pcfMax, 't CO₂/t')
    _range(e, 'addressable', i.get('addressable'), 0, L.addressableMax, 't')
    _range(e, 'rampTargetYear', i.get('rampTargetYear'), current_year, current_year + L.rampYearSpan, '')
    e += yield_errors(i.get('yieldGain'), i.get('yieldGainUnit'), i.get('baselineYield'), L)
    if not i.get('methods'):
        e.append(('methods', 'pick at least one pricing method'))
    return e


def parameters_errors(p: dict[str, Any], current_year: int, limits: Optional[Limits] = None) -> list[tuple[str, str]]:
    L, e = limits or get_limits(), []
    _range(e, 'costPlusMargin', p.get('costPlusMargin'), 0, L.marginMax, '(fraction)')
    _range(e, 'marketingPct', p.get('marketingPct'), 0, L.marketingMax, '(fraction)')
    _range(e, 'dnaPerTon', p.get('dnaPerTon'), 0, L.priceMax, 'USD/t')
    _range(e, 'rampTargetYear', p.get('rampTargetYear'), current_year, current_year + L.rampYearSpan, '')
    _range(e, 'freshnessMonths', p.get('freshnessMonths'), 0, 120, 'months', above=True)
    _range(e, 'staleDays', p.get('staleDays'), 0, 3650, 'days')
    return e
