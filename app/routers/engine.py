from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..engine import (
    Composition,
    EngineInput,
    EngineParams,
    ProductDef,
    SensitivityResult,
    evaluate,
    run_sulphur_sensitivity,
)
from ..engine.run import diff_inputs
from ..schemas import DiffRequest, EngineResult, InputChange, RunInputPatch
from ..store import Store, StoreDep

router = APIRouter(prefix='/engine', tags=['Engine'])


class SensitivityRequest(BaseModel):
    productId: str = 'phos-65-35'
    referenceId: str = 'TSP'
    fromPrice: float = Field(100.0, ge=0.0)
    toPrice: float = Field(1000.0, gt=0.0)
    step: float = Field(50.0, gt=0.0)


@router.post('/run', response_model=EngineResult, summary='Run the pricing engine without saving anything')
def run(body: RunInputPatch, store: Store = StoreDep):  # type: ignore[valid-type]
    """Stateless calculation for previews and derived views (another period, a what-if before it is applied).

    Send only the fields you want to change: everything else comes from the default run input.
    `{}` prices Phosfusion 65-35 against TSP, year to date.
    """
    input = store.make_input(body.model_dump(exclude_unset=True))
    return EngineResult(input=input, output=store.run(input))


@router.post('/diff', response_model=list[InputChange], summary='Inputs that differ between two runs (comment and resolved flags are ignored)')
def diff(body: DiffRequest):
    return diff_inputs(body.before, body.after)


@router.post('/sensitivity', response_model=SensitivityResult, summary='Sulphur price parameter sweep and analytical break-evens')
def sensitivity(body: SensitivityRequest = SensitivityRequest(), store: Store = StoreDep):
    """Run a parameter sweep over the sulphur price and return analytical zero-margin and crossover break-evens."""
    p_row = store.product(body.productId)
    ref_row = store.product(body.referenceId)
    snap = store.snapshots()[0]  # 'today' snapshot
    params = store.params()

    p_def = ProductDef(
        id=p_row.id,
        name=p_row.name,
        recipe=p_row.recipe,
        composition=Composition(**p_row.composition.model_dump()),
        pcf=p_row.pcf,
        pcf_placeholder=p_row.pcfPlaceholder or False,
    )
    ref_def = ProductDef(
        id=ref_row.id,
        name=ref_row.name,
        recipe=ref_row.recipe,
        composition=Composition(**ref_row.composition.model_dump()),
        pcf=ref_row.pcf,
    )

    cost_prices = dict(snap.inputs)
    ref_quote = snap.refPrices.get(ref_row.id)
    ref_price = ref_quote.low if ref_quote else None

    # Evaluate baseline to find anchor price
    eng_in = EngineInput(
        products={p_def.id: p_def, ref_def.id: ref_def},
        product_ids=[p_def.id],
        reference_id=ref_def.id,
        cost_prices=cost_prices,
        reference_price=ref_price,
        params=EngineParams(
            cost_plus_margin=params.costPlusMargin,
            marketing_pct=params.marketingPct,
            include_dna=params.fullCost,
            dna_per_ton=params.dnaPerTon,
            value_share=params.valueShare,
            anchor_method='refMinus',
        ),
        mode='corrected',
    )
    res = evaluate(eng_in)
    anchor_price = res.per_product[p_def.id].anchor_price

    return run_sulphur_sensitivity(
        new_product=p_def,
        ref_product=ref_def,
        cost_prices=cost_prices,
        anchor_price=anchor_price,
        ref_price=ref_price,
        dna_per_ton=params.dnaPerTon if params.fullCost else 0.0,
        marketing_pct=params.marketingPct,
        mode='corrected',
        from_price=body.fromPrice,
        to_price=body.toPrice,
        step=body.step,
    )

