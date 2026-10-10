from fastapi import APIRouter, Body
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError

from ..limits import FieldError

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
from ..schemas import DiffRequest, EngineResult, InputChange, RunInputPatch, Validation
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


@router.post('/validate', response_model=Validation, summary='What running this input would reject, field by field. Nothing is run')
def validate(body: dict = Body(...), store: Store = StoreDep):
    try:
        store.make_input(RunInputPatch.model_validate(body).model_dump(exclude_unset=True))
    except ValidationError as e:
        return {'errors': [{'field': '.'.join(str(x) for x in err['loc']), 'message': err['msg']} for err in e.errors(include_context=False)]}
    except RequestValidationError as e:
        return {'errors': [{'field': '.'.join(str(x) for x in err['loc'] if x not in ('body', 'input')), 'message': err['msg'].removeprefix('Value error, ')} for err in e.errors()]}
    except FieldError as e:
        return {'errors': [{'field': f, 'message': m} for f, m in e.errors]}
    return {'errors': []}


@router.post('/diff', response_model=list[InputChange], summary='Inputs that differ between two runs (comment and resolved flags are ignored)')
def diff(body: DiffRequest):
    return diff_inputs(body.before, body.after)


def sulphur_sweep(store: Store, product_id: str, reference_id: str, from_price: float = 100.0, to_price: float = 1000.0, step: float = 50.0) -> SensitivityResult:
    """Margins of a product and its reference over a range of sulphur prices, with today's other prices and the
    workspace parameters. The product is held at its reference-minus anchor."""
    body = SensitivityRequest(productId=product_id, referenceId=reference_id, fromPrice=from_price, toPrice=to_price, step=step)
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


@router.post('/sensitivity', response_model=SensitivityResult, summary='Sulphur price parameter sweep and analytical break-evens')
def sensitivity(body: SensitivityRequest = SensitivityRequest(), store: Store = StoreDep):
    """Run a parameter sweep over the sulphur price and return analytical zero-margin and crossover break-evens."""
    return sulphur_sweep(store, body.productId, body.referenceId, body.fromPrice, body.toPrice, body.step)
