from fastapi import APIRouter

from ..engine.run import diff_inputs
from ..schemas import DiffRequest, EngineResult, InputChange, RunInputPatch
from ..store import Store, StoreDep

router = APIRouter(prefix='/engine', tags=['Engine'])


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
