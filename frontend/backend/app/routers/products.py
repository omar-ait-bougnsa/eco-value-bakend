from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from ..data.seed import INGREDIENTS
from pydantic import ValidationError

from ..engine.period import YTD, Span, clamp_period
from ..engine.run import INGREDIENT_LABEL, resolve_snapshot
from ..limits import FieldError, product_errors
from ..schemas import CostLine, Family, Ingredient, Product, ProductIn, RecipeCost, RecipeCostRequest, Validation
from ..store import Store, StoreDep, slug, uid

router = APIRouter(tags=['Products'])


def _recipe_cost(store: Store, recipe: dict[str, float], period_from: date | None, period_to: date | None) -> RecipeCost:
    """Recipe × the input prices of a period (year to date when none is given): the same prices the engine reads."""
    if (period_from is None) != (period_to is None):
        raise FieldError([('periodFrom', 'give both periodFrom and periodTo, or neither')])
    if period_from and period_from > period_to:
        raise FieldError([('periodFrom', 'must not be after periodTo')])
    span = clamp_period(Span(period_from or YTD.start, period_to or YTD.end))
    snap = resolve_snapshot(store.ctx(), span.start, span.end)
    lines, missing = [], []
    for id, qty in recipe.items():
        if not qty > 0:
            continue
        price = snap.inputs.get(id)
        if price is None:
            missing.append(INGREDIENT_LABEL.get(id, id))
        lines.append(CostLine(id=id, label=INGREDIENT_LABEL.get(id, id), qty=qty, price=price, usd=None if price is None else qty * price))
    return RecipeCost(
        snapshotId=snap.id, snapshotLabel=snap.label, periodFrom=span.start, periodTo=span.end, asOf=snap.asOf, source=snap.source, lines=lines,
        rawMaterial=None if missing or not lines else sum(l.usd for l in lines),
        unavailable=f'No {snap.label} price for {", ".join(missing)}' if missing else None if lines else 'The recipe has no ingredient with a quantity',
    )


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
    product = Product(id=id, **body.model_dump())
    store.check_product(product, creating=True)
    if store.has_product(id):
        raise HTTPException(409, f'Product {id!r} already exists')
    return store.save_product(product)


@router.post('/products/validate', response_model=Validation, summary='What saving this product would reject, field by field. Nothing is saved')
def validate_product(body: dict = Body(...), id: Optional[str] = Query(None, description='The product being edited, so its own name is not a clash'), store: Store = StoreDep):
    try:
        product = Product(id=id or slug(str(body.get('name') or '')) or 'new', **ProductIn.model_validate(body).model_dump())
    except ValidationError as e:
        return {'errors': [{'field': '.'.join(str(x) for x in err['loc']), 'message': err['msg']} for err in e.errors(include_context=False)]}
    try:
        store.check_product(product, creating=id is None)
    except FieldError as e:
        return {'errors': [{'field': f, 'message': m} for f, m in e.errors]}
    return {'errors': []}


@router.post('/products/recipe-cost', response_model=RecipeCost, summary='Raw-material cost of an unsaved recipe (live preview while editing)')
def recipe_cost(body: RecipeCostRequest, store: Store = StoreDep):
    return _recipe_cost(store, body.recipe, body.periodFrom, body.periodTo)


@router.get('/products/{product_id}', response_model=Product)
def get_product(product_id: str, store: Store = StoreDep):
    return store.product(product_id)


@router.put('/products/{product_id}', response_model=Product, summary='Edit a product. Existing runs are untouched; re-run to use the new recipe')
def update_product(product_id: str, body: ProductIn, store: Store = StoreDep):
    before = store.product(product_id)
    product = Product(id=product_id, **body.model_dump())
    store.check_product(product)
    if before.status == 'quarantined':  # corrected: it can be priced again
        store.audit('restore', 'product', product_id, {'was': before.issues}, actor='user')
    return store.save_product(product)


@router.get('/products/{product_id}/cost', response_model=RecipeCost, summary='Raw-material cost: recipe × input prices of the period (default: year to date)')
def product_cost(
    product_id: str,
    period_from: Optional[date] = Query(None, alias='periodFrom'),
    period_to: Optional[date] = Query(None, alias='periodTo'),
    store: Store = StoreDep,
):
    return _recipe_cost(store, store.product(product_id).recipe, period_from, period_to)
