"""The knowledge base: documents, their chunks and embeddings, and the similarity search over them (RAG.md)."""
import hashlib
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import db
from ..db import DocumentChunkRow, DocumentRow
from .chunker import chunk_document, tokens
from .embeddings import EmbeddingError, get_embedder, pad
from .parser import DocType, classify, date_in_name, parse

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
# What ships with the backend: the sample data files (their kind is read from the name), and the engine's own
# specification as the methodology.
SEED_FILES: tuple[tuple[str, Optional[str]], ...] = (('sample-uploads/*.xlsx', None), ('sample-uploads/*.csv', None), ('engine.md', 'methodology'))


class Passage(BaseModel):
    """A search result: the passage and where it comes from."""
    passage: str
    source: str
    date: Optional[date]
    page: Optional[int]
    pageEnd: Optional[int] = None
    section: Optional[str]
    docType: DocType
    relevanceScore: float
    documentId: str
    chunkId: str

    @property
    def label(self) -> str:
        """What a provenance chip shows: `CRU Fertilizer Week, 24-Sep-2026, p.4`."""
        pages = f'p.{self.page}–{self.pageEnd}' if self.pageEnd and self.pageEnd != self.page else f'p.{self.page}'
        where = pages if self.page else self.section
        return ', '.join(x for x in (self.source, self.date.strftime('%d-%b-%Y') if self.date else None, where) if x)


class DocumentInfo(BaseModel):
    id: str
    name: str
    title: str
    type: DocType
    date: Optional[date]
    pages: Optional[int]
    chunks: int
    status: str
    error: Optional[str]
    uploadId: Optional[str]
    seeded: bool


def _uid(prefix: str, *parts: object) -> str:
    """Ids follow from the file's bytes, so a document keeps its id when it is indexed again (after a reset, for instance)."""
    return prefix + hashlib.sha256(repr(parts).encode()).hexdigest()[:10]


def add_document(session: Session, name: str, data: bytes, *, title: Optional[str] = None, doc_type: Optional[str] = None,
                 doc_date: Optional[date] = None, upload_id: Optional[str] = None, seeded: bool = False) -> DocumentRow:
    """Parse and chunk a file and store it. It is found by `search` once `embed` has run on it.

    The same bytes are stored once: a second call returns the document that is already there.
    Raises `UnsupportedFile` or `UnreadableFile`.
    """
    digest = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(DocumentRow).where(DocumentRow.sha256 == digest))
    if existing is not None:
        return existing
    parsed = parse(name, data)
    # What the classifier reads: the document's title, then its first blocks with their headings.
    sample = ' '.join([parsed.title or '', *(f'{b.section or ""} {b.text or " ".join(" ".join(r) for r in b.rows[:20])}' for b in parsed.blocks[:10])])
    title = title or parsed.title or name
    doc_type = doc_type or classify(name, sample)
    doc_date = doc_date or date_in_name(name)
    doc = DocumentRow(
        id=_uid('d', digest), uploadId=upload_id, name=name, title=title, type=doc_type, docDate=doc_date, pages=parsed.pages,
        sha256=digest, seeded=seeded, status='indexing', error=None, createdAt=datetime.now(timezone.utc),
    )
    doc.chunks = [
        DocumentChunkRow(id=_uid('k', digest, i), position=i, pageNumber=c.page, sectionTitle=c.section, content=c.content,
                         meta={'kind': c.kind, 'tokens': tokens(c.content), 'pageEnd': c.page_end}, embeddingModel=None, embedding=None)
        for i, c in enumerate(chunk_document(parsed, title=title, doc_type=doc_type, doc_date=doc_date))
    ]
    session.add(doc)
    session.commit()
    return doc


def embed(session: Session, document_ids: Optional[list[str]] = None) -> int:
    """Embed the chunks of these documents (of every document when None) with the current model. Returns the chunks embedded.

    A document whose embedding fails is marked `failed` with the reason, and the others still go through.
    """
    embedder = get_embedder()
    query = select(DocumentRow).order_by(DocumentRow.createdAt)
    if document_ids is not None:
        query = query.where(DocumentRow.id.in_(document_ids))
    done = 0
    for doc in session.scalars(query).all():
        try:
            # The title and section go into the vector with the passage: a chunk rarely names its own document.
            vectors = embedder.embed(['\n'.join(x for x in (doc.title, c.sectionTitle, c.content) if x) for c in doc.chunks])
            for chunk, vector in zip(doc.chunks, vectors, strict=True):
                chunk.embedding, chunk.embeddingModel = pad(vector), embedder.name
        except (EmbeddingError, ValueError) as e:
            session.rollback()
            doc.status, doc.error = 'failed', str(e)
            log.warning('Embedding %s failed: %s', doc.name, e)
        else:
            doc.status, doc.error = 'ready', None
            done += len(vectors)
        session.commit()
    return done


def embed_in_background(document_id: str) -> None:
    """For a background task: it outlives the request, so it opens its own session."""
    with db.SessionLocal() as session:
        embed(session, [document_id])


def prepare(session: Session) -> None:
    """On start: load the documents that ship with the backend into an empty knowledge base, then embed whatever is not
    on the current model (new documents, an interrupted upload, or everything after the model changed)."""
    if not session.scalar(select(func.count()).select_from(DocumentRow)):
        for pattern, doc_type in SEED_FILES:
            for path in sorted(ROOT.glob(pattern)):
                add_document(session, path.name, path.read_bytes(), doc_type=doc_type, seeded=True)
    try:
        name = get_embedder().name
    except EmbeddingError as e:  # a setting that cannot work: the rest of the API still starts, and a search says why it cannot
        log.warning('Knowledge base not embedded: %s', e)
        return
    stale = session.scalars(
        select(DocumentChunkRow.documentId).where(or_(DocumentChunkRow.embeddingModel.is_(None), DocumentChunkRow.embeddingModel != name)).distinct()
    ).all()
    if stale:
        embed(session, list(stale))


def _cosine(a: list[float], b: list[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / norm if norm else 0.0


def search(session: Session, query: str, doc_type: Optional[str] = None, limit: int = 4) -> list[Passage]:
    """The passages closest in meaning to `query`, best first. Raises `EmbeddingError` when the query cannot be embedded."""
    embedder = get_embedder()
    vector = pad(embedder.embed([query])[0])
    if not any(vector):
        return []  # nothing but stop words: cosine distance to a zero vector is undefined
    rows = select(DocumentChunkRow, DocumentRow).join(DocumentRow, DocumentRow.id == DocumentChunkRow.documentId).where(DocumentChunkRow.embeddingModel == embedder.name)
    if doc_type:
        rows = rows.where(DocumentRow.type == doc_type)
    if session.get_bind().dialect.name == 'postgresql':
        distance = DocumentChunkRow.embedding.cosine_distance(vector)
        scored = [(c, d, 1 - dist) for c, d, dist in session.execute(rows.add_columns(distance).order_by(distance).limit(limit))]
    else:  # SQLite (the tests) has no vector operators: the ranking is done here
        scored = sorted(((c, d, _cosine(vector, c.embedding)) for c, d in session.execute(rows)), key=lambda x: -x[2])[:limit]
    return [
        Passage(passage=c.content, source=d.title, date=d.docDate, page=c.pageNumber, pageEnd=c.meta.get('pageEnd'), section=c.sectionTitle, docType=d.type,
                relevanceScore=round(float(score), 4), documentId=d.id, chunkId=c.id)
        for c, d, score in scored if score >= embedder.min_score
    ]


def documents(session: Session) -> list[DocumentInfo]:
    """Newest first, with the number of chunks of each."""
    counts = select(DocumentChunkRow.documentId.label('doc'), func.count().label('n')).group_by(DocumentChunkRow.documentId).subquery()
    query = select(DocumentRow, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.doc == DocumentRow.id).order_by(DocumentRow.createdAt.desc(), DocumentRow.name)
    return [info(d, n) for d, n in session.execute(query)]


def info(doc: DocumentRow, chunks: int) -> DocumentInfo:
    return DocumentInfo(id=doc.id, name=doc.name, title=doc.title, type=doc.type, date=doc.docDate, pages=doc.pages, chunks=chunks,
                        status=doc.status, error=doc.error, uploadId=doc.uploadId, seeded=doc.seeded)


def delete_document(session: Session, document_id: str) -> bool:
    """False when there is no such document."""
    session.execute(delete(DocumentChunkRow).where(DocumentChunkRow.documentId == document_id))
    found = session.execute(delete(DocumentRow).where(DocumentRow.id == document_id)).rowcount > 0
    session.commit()
    return found

