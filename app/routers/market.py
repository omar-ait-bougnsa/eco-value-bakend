from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..data.seed import OUTLOOK
from ..engine.period import Span, blend_snapshot, clamp_period, period_label, period_presets, period_weights
from ..schemas import Outlook, Period, PeriodPreset, ResolvedSnapshot, Snapshot
from ..store import Store, StoreDep

router = APIRouter(tags=['Market data'])


@router.get('/snapshots', response_model=list[Snapshot], summary='Yearly market snapshots (input prices and reference FOB prices)')
def list_snapshots(store: Store = StoreDep):
    return store.snapshots()


# Declared before /snapshots/{snapshot_id} so "resolve" is not read as an id.
@router.get('/snapshots/resolve', response_model=ResolvedSnapshot, summary='Market data for an analysis period: day-weighted blend of the yearly snapshots')
def resolve(period_from: date = Query(alias='periodFrom'), period_to: date = Query(alias='periodTo'), store: Store = StoreDep):
    if period_from > period_to:
        raise HTTPException(422, 'periodFrom must not be after periodTo')
    p = clamp_period(Span(period_from, period_to))
    return ResolvedSnapshot(period=Period(from_=p.start, to=p.end), label=period_label(p), weights=period_weights(p), snapshot=blend_snapshot(store.snapshots(), p))


@router.get('/snapshots/{snapshot_id}', response_model=Snapshot)
def get_snapshot(snapshot_id: str, store: Store = StoreDep):
    for s in store.snapshots():
        if s.id == snapshot_id:
            return s
    raise HTTPException(404, f'Snapshot {snapshot_id!r} not found')


@router.get('/periods/presets', response_model=list[PeriodPreset], summary='Period picker presets (year to date, last 12 months, past years)')
def presets():
    return [PeriodPreset(id=i, label=l, period=Period(from_=p.start, to=p.end)) for i, l, p in period_presets()]


@router.get('/outlook', response_model=Outlook, summary='Input price outlook 2026–2034')
def outlook():
    return OUTLOOK
