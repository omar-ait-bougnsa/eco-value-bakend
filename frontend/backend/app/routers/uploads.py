import re
from datetime import date
from typing import Optional

import hashlib
from pathlib import PurePath

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile

from .. import rag

from ..limits import FieldError, get_limits

from ..engine.period import YTD
from ..engine.run import freshness_flags, months_behind_freight
from ..rag.parser import UnreadableFile, UnsupportedFile, parse
from ..schemas import Flag, Freshness, UploadDetection, UploadRecord, UploadType
from ..store import Store, StoreDep, uid

router = APIRouter(tags=['Uploads'])

TYPE_LABEL = {'prices': 'Prices', 'freight': 'Freight', 'agro': 'Agro tests', 'crop': 'Crop prices', 'other': 'Document'}
AFFECTS = {
    'prices': ['TSP FOB price', 'DAP FOB price', 'MAP FOB price'],
    'freight': ['Freight rates'],
    'agro': ['Yield gain', 'Application rate'],
    'crop': ['Crop price'],
    'other': ['Assistant answers (document search)'],  # read by no calculation
}
TABLES = ('.xlsx', '.csv')  # data files: rows are read from them
ALLOWED = (*TABLES, '.pdf', '.docx', '.txt', '.md')  # and documents, which the assistant searches. A legacy .xls cannot be read: it is refused with a way out


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
def list_uploads(type: Optional[UploadType] = None, include_quarantined: bool = Query(False, alias='includeQuarantined', description='Also the records set aside by a review'), store: Store = StoreDep):
    return [u for u in store.uploads(quarantined=include_quarantined) if type is None or u.type == type]


def _read(name: str, data: bytes) -> list[tuple[Optional[str], list[list[str]]]]:
    """The tables of the file as (sheet, rows). Empty when it has none, or cannot be read (a legacy .xls, a damaged file)."""
    try:
        return [(b.section, b.rows) for b in parse(name, data).blocks if b.rows]
    except (UnsupportedFile, UnreadableFile):
        return []


def _blocks(name: str, data: bytes) -> int:
    """How many pieces of text or tables the file has. 0 when it cannot be read."""
    try:
        return len(parse(name, data).blocks)
    except (UnsupportedFile, UnreadableFile):
        return 0


def _latest_date(tables) -> Optional[date]:
    """The last day the rows cover: the latest date in a cell, today at most."""
    found = []
    for _, rows in tables:
        for row in rows:
            for cell in row:
                m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})(?: .*)?', cell)
                try:
                    found.append(date(int(m[1]), int(m[2]), int(m[3]))) if m else None
                except ValueError:
                    continue
    past = [d for d in found if d <= date.today()]
    return max(past, default=None)


def _inverted_quote(tables) -> Optional[str]:
    """A row whose low quote is above its high one."""
    for _, rows in tables:
        header = [c.lower() for c in rows[0]]
        low = next((i for i, c in enumerate(header) if re.search(r'\blow\b', c)), None)
        high = next((i for i, c in enumerate(header) if re.search(r'\bhigh\b', c)), None)
        if low is None or high is None:
            continue
        for row in rows[1:]:
            try:
                lo, hi = float(row[low]), float(row[high])
            except (ValueError, IndexError):
                continue
            if lo > hi:
                return f'{row[0]} quote: low {lo:g} > high {hi:g}. The low quote is higher than the high quote — check the file. Low will be used.'
    return None


def _type(name: str, tables) -> UploadType:
    """From the words of the file name, then of its column headers. A file that is neither prices, freight, trials nor
    crop prices is a document: searched by the assistant, used in no calculation."""
    for text in (name.lower(), ' '.join(c.lower() for _, rows in tables for c in rows[0])):
        if re.search('freight|route|vessel|cargo', text):
            return 'freight'
        if re.search(r'agro|trial|yield|t/ha', text):
            return 'agro'
        if 'crop' in text:
            return 'crop'
        if re.search(r'price|argus|fob|quote|\blow\b', text):
            return 'prices'
    return 'other'


def _review(store: Store, name: str, data: bytes) -> tuple[UploadDetection, list[tuple[str, str]]]:
    """What the file is, read from its content, and what stops it from being used (field, message)."""
    name = PurePath(name.replace('\\', '/')).name.strip()
    problems: list[tuple[str, str]] = []
    if not re.sub(r'\.(xlsx|xls|csv)$', '', name, flags=re.I).strip(' .'):
        problems.append(('file', 'has no file name'))
    if not name.lower().endswith(ALLOWED):
        problems.append(('file', f'only {", ".join(ALLOWED)} files are accepted' + (': save the workbook as .xlsx' if name.lower().endswith('.xls') else '')))
    size = len(data)
    if size == 0:
        problems.append(('file', 'is empty'))
    elif size > get_limits().uploadMaxBytes:
        problems.append(('file', f'is larger than {get_limits().uploadMaxBytes / 1e6:g} MB'))
    tables = [] if problems else _read(name, data)
    blocks = 0 if problems else _blocks(name, data)
    if not problems and not blocks:
        problems.append(('file', f'could not be read as a {PurePath(name).suffix.lower()} file: it is damaged, empty, or not what its extension says'))
    # Only a file with rows can be data for the calculations.
    type = _type(name, tables) if tables else 'other'
    argus = type == 'prices' and 'argus' in name.lower()
    d = _date_in(name)
    through = _latest_date(tables) or d
    current = store.uploads()
    candidate = UploadRecord(id='preview', name=name or 'unnamed', type=type, uploadedAt=date.today(), fileDate=d, dataThrough=through)
    rows = sum(len(r) - 1 for _, r in tables)
    sheets = [s for s, _ in tables if s]
    found = UploadDetection(
        name=name or 'unnamed',
        size=f'{size / 1e6:.1f} MB' if size > 1e6 else f'{max(1, round(size / 1024))} KB',
        type=type,
        typeLabel=('Prices — Argus FOB Morocco' if argus else 'Prices') if type == 'prices' else TYPE_LABEL[type],
        fileDate=d, dataThrough=through,
        # What was read: nothing is claimed about a file that could not be opened.
        series=(f'{rows} row{"" if rows == 1 else "s"}' + (f' · {len(sheets)} sheet{"" if len(sheets) == 1 else "s"}: {", ".join(sheets[:4])}' if sheets else '')) if tables else f'{blocks} section{"" if blocks == 1 else "s"} of text' if blocks else 'Not read',
        affects=AFFECTS[type],
        resolves=not problems and 'D1' in _flags(store, current) and 'D1' not in _flags(store, [candidate, *current]),
        warn=_inverted_quote(tables) if tables else None,
        problems=[m for _, m in problems],
        duplicateOf=(dup.id if (dup := store.upload_with_hash(hashlib.sha256(data).hexdigest())) else None) if not problems else None,
    )
    return found, problems


@router.post('/uploads/detect', response_model=UploadDetection, summary='Review a file before using it: what was read from it, and what stops it from being used')
def detect(file: UploadFile = File(description='.xlsx, .csv, .pdf, .docx, .txt or .md'), store: Store = StoreDep):
    """Nothing is saved. `problems` lists why the file would be refused; `duplicateOf` is the upload that already holds this exact file."""
    return _review(store, file.filename or '', file.file.read())[0]


@router.post('/uploads', response_model=UploadRecord, status_code=201, summary='Use a file in simulations. The same file sent again returns the upload it already is (200)')
def create_upload(response: Response, background: BackgroundTasks, file: UploadFile = File(description='.xlsx, .csv, .pdf, .docx, .txt or .md'), store: Store = StoreDep):
    """The record is made from the file itself: its name, what was read from it and its SHA-256. A file that cannot be read is refused."""
    data = file.file.read()
    found, problems = _review(store, file.filename or '', data)
    if problems:
        raise FieldError(problems)
    digest = hashlib.sha256(data).hexdigest()
    existing = store.upload_with_hash(digest)
    if existing:  # idempotent: the same bytes are the same upload
        store.audit('duplicate-upload', 'upload', existing.id, {'name': found.name}, actor='user')
        store.db.commit()
        response.status_code = 200
        return existing.model_copy(update={'duplicate': True})
    saved = store.add_upload(UploadRecord(
        id=uid('u'), uploadedAt=date.today(), name=found.name, type=found.type, fileDate=found.fileDate, dataThrough=found.dataThrough,
        detail=found.series, sizeBytes=len(data), contentHash=digest,
    ))
    # The same step puts the file in the knowledge base, so the assistant can answer from it: it does not depend on a
    # second request from the browser. Its embeddings are computed after the response.
    doc = rag.add_document(store.db, found.name, data, upload_id=saved.id)
    if doc.status != 'ready':
        background.add_task(rag.embed_in_background, doc.id)
    return saved.model_copy(update={'documentId': doc.id})


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
        behind=months_behind_freight(uploads, store.params()),
    )
