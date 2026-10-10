from fastapi import APIRouter
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from ..data import seed
from ..schemas import Parameters, ParametersPatch, RunInput
from ..engine.period import CURRENT_YEAR
from ..limits import FieldError, parameters_errors
from ..store import Store, StoreDep

router = APIRouter(tags=['Parameters'])


@router.get('/parameters', response_model=Parameters, summary='Global defaults used for new runs')
def get_parameters(store: Store = StoreDep):
    return store.params()


@router.patch('/parameters', response_model=Parameters, summary='Change some defaults. Existing runs are untouched')
def patch_parameters(body: ParametersPatch, store: Store = StoreDep):  # type: ignore[valid-type]
    merged = {**store.params().model_dump(), **body.model_dump(exclude_unset=True)}
    try:
        params = Parameters.model_validate(merged)
    except ValidationError as e:
        raise RequestValidationError([{**err, 'loc': ('body', *err['loc'])} for err in e.errors(include_context=False)])
    errors = parameters_errors(params.model_dump(), CURRENT_YEAR)
    if errors:
        raise FieldError(errors)
    return store.set_params(params)


@router.get('/parameters/defaults', response_model=Parameters, summary='The default value of every parameter')
def default_parameters():
    return seed.default_params()


@router.post('/parameters/reset', response_model=Parameters, summary='Restore the default parameters')
def reset_parameters(store: Store = StoreDep):
    return store.set_params(seed.default_params())


@router.get('/parameters/default-run-input', response_model=RunInput, summary='The run input a new simulation starts from (Configure run form)')
def default_run_input(store: Store = StoreDep):
    return store.make_input({})
