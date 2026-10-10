import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from . import settings  # noqa: F401  (reads .env before anything looks at the environment)
from . import db, rag
from .routers import agent, engine, market, parameters, products, simulations, uploads
from .routers import rag as knowledge
from .db import AuditRow
from .limits import FieldError, Limits, get_limits
from .store import Store, StoreDep, init_db


# The app's own logs: job transitions and model calls, each with the job id. Uvicorn only sets up its own loggers.
_log = logging.getLogger('evs')
if not _log.handlers:
    class _JobId(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            from .agent.jobs import current_job
            record.job = current_job.get()
            return True

    _handler = logging.StreamHandler()
    _handler.addFilter(_JobId())
    _handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s [%(job)s] %(message)s'))
    _log.addHandler(_handler)
    _log.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with db.SessionLocal() as session:
        rag.prepare(session)
    yield


app = FastAPI(
    title='Eco Value Simulator API',
    version='0.1.0',
    lifespan=lifespan,
    description=(
        'Pricing & margin simulator for new OCP fertilizers. '
        'The engine calculates with validated formulas; these endpoints serve the data the frontend currently mocks.\n\n'
        'Data is stored in PostgreSQL. An empty database is loaded with the demo data on start; '
        '`POST /api/reset` restores it.'
    ),
)

# Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def problems(errors: list[tuple[str, str]]) -> JSONResponse:
    """Rejected input: 400 with one entry per field. `detail` is the same in one line, for a message box."""
    return JSONResponse({'detail': '; '.join(f'{f}: {m}' if f else m for f, m in errors), 'errors': [{'field': f, 'message': m} for f, m in errors]}, status_code=400)


def as_problems(exc: RequestValidationError) -> list[tuple[str, str]]:
    # The default handler echoes the rejected value back, which fails on NaN / Infinity (not valid JSON).
    return [('.'.join(str(x) for x in e['loc'] if x not in ('body', 'query', 'input')), e['msg'].removeprefix('Value error, ')) for e in exc.errors()]


@app.exception_handler(RequestValidationError)
def invalid_request(request, exc: RequestValidationError):
    return problems(as_problems(exc))


@app.exception_handler(FieldError)
def out_of_bounds(request, exc: FieldError):
    return problems(exc.errors)


for r in (products, market, parameters, uploads, engine, simulations, agent, knowledge):
    app.include_router(r.router, prefix='/api')



@app.post('/api/reset', status_code=204, tags=['System'], summary='Delete everything and reload the demo data (products, uploads, parameters, simulations, knowledge documents)')
def reset(store: Store = StoreDep):
    store.reset()
    rag.prepare(store.db)


@app.get('/api/limits', response_model=Limits, tags=['System'], summary='Business limits of the inputs: what the API accepts, for the forms to show')
def limits():
    return get_limits()


@app.get('/api/audit', tags=['System'], summary='Quarantines, restores and duplicate uploads, newest first')
def audit(store: Store = StoreDep, limit: int = 100):
    from sqlalchemy import select
    rows = store.db.scalars(select(AuditRow).order_by(AuditRow.at.desc()).limit(limit))
    return [{'id': r.id, 'at': r.at, 'actor': r.actor, 'action': r.action, 'entity': r.entity, 'entityId': r.entityId, 'detail': r.detail} for r in rows]


@app.get('/api/health', tags=['System'])
def health():
    return {'status': 'ok'}


@app.get('/', include_in_schema=False)
def root():
    return RedirectResponse('/docs')
