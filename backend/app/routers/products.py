from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..data.seed import INGREDIENTS
from ..engine.period import YTD
from ..engine.run import cost_lines, resolve_snapshot
from ..schemas import Family, Ingredient, Product, ProductIn, RecipeCost, RecipeCostRequest
from ..store import Store, StoreDep, slug, uid

router = APIRouter(tags=['Products'])


def _recipe_cost(store: Store, recipe: dict[str, float], period_from: date | None, period_to: date | None) -> RecipeCost:
    if (period_from is None) != (period_to is None):
        raise HTTPException(422, 'Give both periodFrom and periodTo, or neither')
    if period_from and period_from > period_to:
        raise HTTPException(422, 'periodFrom must not be after periodTo')
    snap = resolve_snapshot(store.ctx(), period_from or YTD.start, period_to or YTD.end)
    lines = cost_lines(recipe, snap)
    return RecipeCost(snapshotId=snap.id, snapshotLabel=snap.label, lines=lines, rawMaterial=sum(l.usd for l in lines))


@router.get('/ingredients', response_model=list[Ingredient], summary='Raw materials a recipe can use')
def list_ingredients():
    return INGREDIENTS


@router.get('/products', response_model=list[Product], summary='Product library')
def list_products(
    family: Optional[Family] = None,
    q: Optional[str] = Query(None, description='Case-insensitive search on the name'),
    store: Store = StoreDep,
):
    return [p for p in store.products() if (family is None or p.family == family) and (not q or q.lower() in p.name.lower())]


@router.post('/products', response_model=Product, status_code=201, summary='Add a product (id is derived from the name)')
def create_product(body: ProductIn, store: Store = StoreDep):
    id = slug(body.name) or uid('p')  # names without Latin letters or digits get a generated id
    if store.has_product(id):
        raise HTTPException(409, f'Product {id!r} already exists')
    return store.save_product(Product(id=id, **body.model_dump()))


@router.post('/products/recipe-cost', response_model=RecipeCost, summary='Raw-material cost of an unsaved recipe (live preview while editing)')
def recipe_cost(body: RecipeCostRequest, store: Store = StoreDep):
    return _recipe_cost(store, body.recipe, body.periodFrom, body.periodTo)


@router.get('/products/{product_id}', response_model=Product)
def get_product(product_id: str, store: Store = StoreDep):
    return store.product(product_id)


@router.put('/products/{product_id}', response_model=Product, summary='Edit a product. Existing runs are untouched; re-run to use the new recipe')
def update_product(product_id: str, body: ProductIn, store: Store = StoreDep):
    store.product(product_id)
    return store.save_product(Product(id=product_id, **body.model_dump()))


@router.get('/products/{product_id}/cost', response_model=RecipeCost, summary='Raw-material cost: recipe × input prices of the period (default: year to date)')
def product_cost(
    product_id: str,
    period_from: Optional[date] = Query(None, alias='periodFrom'),
    period_to: Optional[date] = Query(None, alias='periodTo'),
    store: Store = StoreDep,
):
    return _recipe_cost(store, store.product(product_id).recipe, period_from, period_to)
