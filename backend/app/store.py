"""Application state, stored in the database. Replaces the frontend's Zustand store (`src/store/app.ts`)."""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Iterator
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from . import db, migrations
from .data import seed
from .db import AuditRow, JobRow, DocumentChunkRow, DocumentRow, ParametersRow, ProductRow, RunRow, SimulationRow, SnapshotRow, UploadRow
from .engine.period import CURRENT_YEAR, YTD
from .limits import FieldError, product_errors, run_input_errors
from .engine.run import Ctx, diff_inputs, run_engine
from .schemas import Parameters, Product, Run, RunInput, RunOutput, Snapshot, UploadRecord


def uid(prefix: str) -> str:
    return f'{prefix}{uuid4().hex[:10]}'


def slug(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, session: Session) -> None:
        self.db = session

    def _commit(self, conflict: str) -> None:
        """Commit; 409 when another request wrote the same key first."""
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409, conflict)

    # ── products ──

    def products(self) -> list[Product]:
        return [Product.model_validate(r) for r in self.db.scalars(select(ProductRow).order_by(ProductRow.position))]

    def product(self, id: str) -> Product:
        row = self.db.get(ProductRow, id)
        if row is None:
            raise HTTPException(404, f'Product {id!r} not found')
        return Product.model_validate(row)

    def check_product(self, product: Product, creating: bool = False) -> None:
        """The business bounds, and a name no other product has (whatever the case). Raises FieldError."""
        errors = product_errors(product.model_dump())
        same_name = select(ProductRow).where(func.lower(ProductRow.name) == product.name.lower())
        clash = self.db.scalars(same_name if creating else same_name.where(ProductRow.id != product.id)).first()
        if clash is not None:
            errors.append(('name', f'is already the name of another product ({clash.id})'))
        if errors:
            raise FieldError(errors)

    def audit(self, action: str, entity: str, entity_id: str, detail: dict, actor: str = 'system') -> None:
        self.db.add(AuditRow(id=uid('a'), at=now(), actor=actor, action=action, entity=entity, entityId=entity_id, detail=detail))

    def has_product(self, id: str) -> bool:
        return self.db.get(ProductRow, id) is not None

    def save_product(self, product: Product) -> Product:
        """Insert, or update in place when the id exists."""
        row = self.db.get(ProductRow, product.id)
        if row is None:
            last = self.db.scalar(select(func.max(ProductRow.position)))
            self.db.add(ProductRow(position=(last if last is not None else -1) + 1, **product.model_dump()))
        else:
            for k, v in product.model_dump(exclude={'id'}).items():
                setattr(row, k, v)
        self._commit(f'Product {product.id!r} already exists')
        return product

    # ── market data, uploads, parameters ──

    def snapshots(self) -> list[Snapshot]:
        return [Snapshot.model_validate(r) for r in self.db.scalars(select(SnapshotRow).order_by(SnapshotRow.position))]

    def uploads(self, quarantined: bool = False) -> list[UploadRecord]:
        """Newest first. Quarantined records are kept but read by nothing, unless asked for."""
        rows = self.db.scalars(select(UploadRow).order_by(UploadRow.createdAt.desc()))
        return [UploadRecord.model_validate(r) for r in rows if quarantined or r.status != 'quarantined']

    def upload_with_hash(self, content_hash: str) -> UploadRecord | None:
        rows = self.db.scalars(select(UploadRow).where(UploadRow.contentHash == content_hash))
        row = next((r for r in rows if r.status != 'quarantined'), None)
        return UploadRecord.model_validate(row) if row is not None else None

    def add_upload(self, upload: UploadRecord) -> UploadRecord:
        self.db.add(UploadRow(createdAt=now(), **upload.model_dump(exclude={'duplicate', 'documentId'})))
        self.db.commit()
        return upload

    def params(self) -> Parameters:
        return Parameters.model_validate(self.db.get(ParametersRow, 1))

    def set_params(self, params: Parameters) -> Parameters:
        row = self.db.get(ParametersRow, 1)
        for k, v in params.model_dump().items():
            setattr(row, k, v)
        self.db.commit()
        return params

    def ctx(self) -> Ctx:
        return Ctx(products=self.products(), snapshots=self.snapshots(), uploads=self.uploads(), params=self.params())

    # ── simulations ──

    def sims(self) -> list[tuple[SimulationRow, int]]:
        """Simulations with their number of runs, newest first."""
        runs = select(RunRow.simulationId.label('sim'), func.count().label('n')).group_by(RunRow.simulationId).subquery()
        query = select(SimulationRow, func.coalesce(runs.c.n, 0)).outerjoin(runs, runs.c.sim == SimulationRow.id)
        return [(sim, n) for sim, n in self.db.execute(query.order_by(SimulationRow.createdAt.desc()))]

    def sim(self, id: str) -> SimulationRow:
        row = self.db.get(SimulationRow, id)
        if row is None:
            raise HTTPException(404, f'Simulation {id!r} not found')
        return row

    def add_sim(self, title: str) -> SimulationRow:
        sim = SimulationRow(id=uid('s'), title=title, createdAt=now(), runs=[])
        self.db.add(sim)
        self.db.commit()
        return sim

    def rename_sim(self, sim: SimulationRow, title: str) -> SimulationRow:
        sim.title = title
        self.db.commit()
        return sim

    def delete_sim(self, sim: SimulationRow) -> None:
        self.db.delete(sim)
        self.db.commit()

    def duplicate_sim(self, src: SimulationRow) -> SimulationRow:
        copied = ('version', 'input', 'output', 'createdAt', 'createdBy', 'summary', 'changed', 'editedKeys', 'productSig')
        sim = SimulationRow(id=uid('s'), title=f'{src.title} (copy)', createdAt=now(),
                            runs=[RunRow(id=uid('r'), **{k: getattr(r, k) for k in copied}) for r in src.runs])
        self.db.add(sim)
        self.db.commit()
        return sim

    # ── runs ──

    def default_input(self, overrides: dict | None = None) -> dict:
        """Starting point of a first run. Agronomy and carbon inputs come from the lead product and the
        reference chosen in `overrides`, with the workbook figures where a product has none."""
        p = self.params()
        over = overrides or {}
        ids = over.get('productIds') or ['phos-65-35']
        ref_id = over.get('referenceId') or p.defaultReference
        lead, ref = self.db.get(ProductRow, ids[0]), self.db.get(ProductRow, ref_id)

        def pick(row, attr, fallback):
            v = getattr(row, attr, None)
            return fallback if v is None else v

        return dict(
            productIds=ids, referenceId=ref_id, periodFrom=YTD.start, periodTo=YTD.end,
            methods=['costPlus', 'market', 'value', 'refMinus'],
            costPlusMargin=p.costPlusMargin, marketingPct=p.marketingPct, fullCost=p.fullCost, dnaPerTon=p.dnaPerTon,
            valueShare=p.valueShare, priceType=p.priceType, cropPrice=seed.TARGET_CROP_PRICE,
            yieldGain=pick(lead, 'yieldGain', 0.12), yieldGainUnit=pick(lead, 'yieldGainUnit', 't/ha'), baselineYield=getattr(lead, 'baselineYield', None),
            appRateNew=pick(lead, 'appRate', 0.162), pcfNew=pick(lead, 'pcf', 0.5),
            appRateRef=pick(ref, 'appRate', 0.13), pcfRef=pick(ref, 'pcf', 0.7),
            carbonMarket=p.carbonMarket, carbonPrice=0, marketShare=p.marketShare, rampTargetYear=p.rampTargetYear,
            addressable=seed.ADDRESSABLE_MARKET_T, benchmark=None, anchor='refMinus', refCostOverride=None,
            comment='', resolved={},
        )

    def make_input(self, overrides: dict, base: RunInput | None = None) -> RunInput:
        """Overrides on top of `base` (or the defaults derived from the current parameters). 422 on invalid input.

        `resolved` is merged key by key, so resolving one flag keeps the earlier answers.
        """
        start = base.model_dump() if base else self.default_input(overrides)
        merged = {**start, **overrides}
        if isinstance(overrides.get('resolved'), dict):
            merged['resolved'] = {**start['resolved'], **overrides['resolved']}
        try:
            input = RunInput.model_validate(merged)
        except ValidationError as e:
            raise RequestValidationError([{**err, 'loc': ('body', 'input', *err['loc'])} for err in e.errors(include_context=False)])
        rows = {i: self.db.get(ProductRow, i) for i in dict.fromkeys([*input.productIds, input.referenceId])}
        missing = [i for i, r in rows.items() if r is None]
        if missing:
            raise FieldError([('productIds', f'unknown product id(s): {", ".join(missing)}')])
        held = [i for i, r in rows.items() if r.status == 'quarantined']
        if held:
            raise FieldError([('productIds', f'{", ".join(held)} is quarantined and cannot be priced until it is corrected')])
        errors = run_input_errors(input.model_dump(), min(CURRENT_YEAR, input.periodFrom.year))
        if errors:
            raise FieldError(errors)
        return input

    def run(self, input: RunInput, ctx: Ctx | None = None) -> RunOutput:
        """Run the engine. 422 when the inputs are so large that a result is not a finite number."""
        try:
            return run_engine(input, ctx or self.ctx())
        except (ValidationError, OverflowError):
            raise HTTPException(400, 'These inputs produce a result that is not a finite number')

    def add_run(self, sim: SimulationRow, input: RunInput, by: str, summary: str, commit: bool = True) -> Run:
        """Run the engine and append the result as the simulation's next version."""
        ctx = self.ctx()
        prev = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None
        first = RunInput.model_validate(sim.runs[0].input) if sim.runs else None
        by_id = {p.id: p for p in ctx.products}
        sig = {i: json.dumps([by_id[i].recipe, by_id[i].composition.model_dump()], separators=(',', ':')) for i in input.productIds}
        run = Run(
            id=uid('r'), version=len(sim.runs) + 1, input=input, output=self.run(input, ctx), productSig=sig,
            createdAt=now(), createdBy=by, summary=summary,
            changed=[d.key for d in diff_inputs(prev, input)] if prev else [],
            editedKeys=[d.key for d in diff_inputs(first, input)] if first else [],
        )
        sim.runs.append(RunRow(**{**run.model_dump(), 'input': input.model_dump(mode='json'),
                                  'output': run.output.model_dump(mode='json', by_alias=True)}))
        if commit:
            self._commit('Another run was saved for this simulation at the same moment. Send the request again')
        return run

    # ── seed ──

    def seed(self) -> None:
        self.db.add_all(ProductRow(position=i, **p.model_dump()) for i, p in enumerate(seed.products()))
        self.db.add_all(SnapshotRow(position=i, **s.model_dump()) for i, s in enumerate(seed.SNAPSHOTS))
        loaded = datetime(seed.TODAY.year, seed.TODAY.month, seed.TODAY.day, tzinfo=timezone.utc)
        self.db.add_all(UploadRow(createdAt=loaded - timedelta(seconds=i), **u.model_dump(exclude={'duplicate', 'documentId'})) for i, u in enumerate(seed.uploads()))
        self.db.add(ParametersRow(id=1, **seed.default_params().model_dump()))
        self.db.flush()
        for id, title, created, over in (
            ('s2', 'Phosfusion 50-50 vs DAP', datetime(2026, 10, 1, 10, 12, tzinfo=timezone.utc), {'productIds': ['phos-50-50'], 'referenceId': 'DAP', 'resolved': {'S1': 'n/a'}}),
            ('s3', 'Sulphur spike sensitivity', datetime(2026, 9, 28, 16, 40, tzinfo=timezone.utc), {'periodFrom': '2025-01-01', 'periodTo': '2025-12-31', 'resolved': {'S1': 'n/a'}}),
        ):
            sim = SimulationRow(id=id, title=title, createdAt=created, runs=[])
            self.db.add(sim)
            self.add_run(sim, self.make_input(over), 'user', 'Initial run', commit=False)
        self.db.commit()

    def reset(self) -> None:
        """Drop every row and load the demo data again. The knowledge base is left empty: `rag.prepare` loads its documents."""
        for table in (JobRow, DocumentChunkRow, DocumentRow, RunRow, SimulationRow, UploadRow, ProductRow, SnapshotRow, ParametersRow, AuditRow):
            self.db.execute(delete(table))
        self.db.expunge_all()
        self.seed()


def init_db() -> None:
    """Create missing tables and load the demo data into an empty database."""
    try:
        migrations.upgrade(db.engine)  # columns added since the tables were made
        db.Base.metadata.create_all(db.engine)
    except DBAPIError as e:
        if 'vector' in str(e.orig):
            raise RuntimeError('This PostgreSQL has no pgvector extension, which the knowledge base needs. '
                               'Use the pgvector/pgvector:pg17-trixie image (see docker-compose.yml).') from e
        raise
    with db.SessionLocal() as session:
        if session.get(ParametersRow, 1) is None:
            Store(session).seed()


def get_store() -> Iterator[Store]:
    with db.SessionLocal() as session:
        yield Store(session)


StoreDep = Depends(get_store)
