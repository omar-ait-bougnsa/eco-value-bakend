import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..engine.period import YTD
from ..engine.run import freshness_flags
from ..schemas import Flag, Freshness, UploadDetection, UploadIn, UploadRecord, UploadType
from ..store import Store, StoreDep, uid

router = APIRouter(tags=['Uploads'])

TYPE_LABEL = {'prices': 'Prices', 'freight': 'Freight', 'agro': 'Agro tests', 'crop': 'Crop prices'}
AFFECTS = {
    'prices': ['TSP FOB price', 'DAP FOB price', 'MAP FOB price'],
    'freight': ['Freight rates'],
    'agro': ['Yield gain', 'Application rate'],
    'crop': ['Crop price'],
}
SERIES = {'prices': 'DAP, MAP, TSP · low / high · 3 products', 'freight': '10 commodity tabs', 'agro': 'Trials by crop', 'crop': '1 crop'}
ALLOWED = ('.xlsx', '.xls', '.csv')


def _date_in(name: str) -> date:
    """dd-mm-yyyy or yyyy-mm-dd anywhere in the filename, else today."""
    found = [(m[3], m[2], m[1]) for m in re.finditer(r'(\d{2})-(\d{2})-(\d{4})', name)]
    found += [(m[1], m[2], m[3]) for m in re.finditer(r'(\d{4})-(\d{2})-(\d{2})', name)]
    for y, m, d in found:
        try:
            return min(date(int(y), int(m), int(d)), date.today())
        except ValueError:
            continue
    return date.today()


def _flags(store: Store, uploads: list[UploadRecord]) -> dict[str, Flag]:
    return {f.code: f for f in freshness_flags(uploads, store.params(), YTD)}


@router.get('/uploads', response_model=list[UploadRecord], summary='Data files the simulator reads, newest first')
def list_uploads(type: Optional[UploadType] = None, store: Store = StoreDep):
    return [u for u in store.uploads() if type is None or u.type == type]


@router.post('/uploads/detect', response_model=UploadDetection, summary='Review a file before using it: detected type, dates, and what it affects')
def detect(file: UploadFile = File(description='.xlsx, .xls or .csv'), store: Store = StoreDep):
    name = file.filename or ''
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(415, 'Only .xlsx, .xls and .csv files are accepted')
    size = file.size if file.size is not None else len(file.file.read())
    n = name.lower()
    type = 'freight' if 'freight' in n else 'agro' if re.search('agro|trial', n) else 'crop' if 'crop' in n else 'prices'
    argus = type == 'prices' and 'argus' in n
    d = _date_in(name)
    current = store.uploads()
    candidate = UploadRecord(id='preview', name=name, type=type, uploadedAt=date.today(), fileDate=d, dataThrough=d)
    return UploadDetection(
        name=name,
        size=f'{size / 1e6:.1f} MB' if size > 1e6 else f'{max(1, round(size / 1024))} KB',
        type=type,
        typeLabel=('Prices — Argus FOB Morocco' if argus else 'Prices — CRU weekly averages') if type == 'prices' else TYPE_LABEL[type],
        fileDate=d, dataThrough=d, series=SERIES[type], affects=AFFECTS[type],
        resolves='D1' in _flags(store, current) and 'D1' not in _flags(store, [candidate, *current]),
        warn='TSP FOB quote: low 710 > high 691. The low quote is higher than the high quote — check the Argus file. Low will be used.' if argus else None,
    )


@router.post('/uploads', response_model=UploadRecord, status_code=201, summary='Use a reviewed file in simulations')
def create_upload(body: UploadIn, store: Store = StoreDep):
    if max(body.fileDate, body.dataThrough) > date.today():
        raise HTTPException(422, 'fileDate and dataThrough cannot be in the future')
    return store.add_upload(UploadRecord(id=uid('u'), uploadedAt=date.today(), **body.model_dump()))


@router.get('/uploads/freshness', response_model=Freshness, summary='Latest upload and the data-freshness flags (D1 prices vs freight gap, D2 stale uploads)')
def freshness(store: Store = StoreDep):
    uploads = store.uploads()
    flags = _flags(store, uploads)
    dated = [u for u in uploads if u.type in ('prices', 'freight')]
    d1, d2 = flags.get('D1'), flags.get('D2')
    return Freshness(
        latest=max(uploads, key=lambda u: u.uploadedAt, default=None),
        through=max(dated, key=lambda u: u.dataThrough, default=None),
        warn=bool(d1 or d2), d1=d1, d2=d2,
    )
