from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from . import db, rag
from .routers import agent, engine, market, parameters, products, simulations, uploads
from .routers import rag as knowledge
from .store import Store, StoreDep, init_db


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


@app.exception_handler(RequestValidationError)
def invalid_request(request, exc: RequestValidationError):
    # The default handler echoes the rejected value back, which fails on NaN / Infinity (not valid JSON).
    return JSONResponse({'detail': [{'type': e['type'], 'loc': list(e['loc']), 'msg': e['msg']} for e in exc.errors()]}, status_code=422)


for r in (products, market, parameters, uploads, engine, simulations, agent, knowledge):
    app.include_router(r.router, prefix='/api')



@app.post('/api/reset', status_code=204, tags=['System'], summary='Delete everything and reload the demo data (products, uploads, parameters, simulations, knowledge documents)')
def reset(store: Store = StoreDep):
    store.reset()
    rag.prepare(store.db)


@app.get('/api/health', tags=['System'])
def health():
    return {'status': 'ok'}


@app.get('/', include_in_schema=False)
def root():
    return RedirectResponse('/docs')
