from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from .. import rag
from ..db import UploadRow
from ..rag import DocType, DocumentInfo, EmbeddingError, Passage
from ..store import Store, StoreDep

router = APIRouter(prefix='/knowledge', tags=['Knowledge'])

MAX_BYTES = 20 * 1024 * 1024


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    docType: Optional[DocType] = None
    limit: int = Field(4, ge=1, le=20)


class SearchResponse(BaseModel):
    results: list[Passage]
    model: str = Field(description='Embedding model the search ran on')


class Reindexed(BaseModel):
    documents: int
    chunks: int
    model: str


def _unavailable(e: EmbeddingError) -> HTTPException:
    return HTTPException(503, f'Knowledge search is unavailable: {e}')


@router.post('/search', response_model=SearchResponse, summary='Passages of the indexed documents closest in meaning to a question')
def search(body: SearchRequest, store: Store = StoreDep):
    """The search the agent's `search_knowledge` tool runs, for debugging and for a search box in the UI."""
    try:
        return SearchResponse(results=rag.search(store.db, body.query, body.docType, body.limit), model=rag.get_embedder().name)
    except EmbeddingError as e:
        raise _unavailable(e)


@router.get('/documents', response_model=list[DocumentInfo], summary='Indexed documents, newest first, with their page and chunk counts')
def list_documents(store: Store = StoreDep):
    return rag.documents(store.db)


@router.post('/documents', response_model=DocumentInfo, status_code=201, summary='Index a document: .pdf, .xlsx, .csv, .docx, .txt or .md')
def add_document(
    response: Response,
    background: BackgroundTasks,
    file: UploadFile = File(description='At most 20 MB'),
    uploadId: Optional[str] = Form(None, description='The upload this file belongs to (POST /uploads), when it is a data file'),
    docType: Optional[DocType] = Form(None, description='Detected from the name and the text when left out'),
    title: Optional[str] = Form(None, description='How the document is named in citations. The filename when left out'),
    docDate: Optional[date] = Form(None, description='Read from the filename when left out'),
    store: Store = StoreDep,
):
    """The file is read and cut into chunks at once, so a file that cannot be read is refused here.

    The embeddings are computed after the response: the document is `indexing`, then `ready` (or `failed`, with the
    reason) in `GET /knowledge/documents`. A file that is already indexed is returned as it is, with status 200.
    """
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'The file is larger than 20 MB')
    if uploadId is not None and store.db.get(UploadRow, uploadId) is None:
        raise HTTPException(404, f'Upload {uploadId!r} not found')
    known = {d.id for d in rag.documents(store.db)}
    try:
        doc = rag.add_document(store.db, file.filename or 'document', data, title=title, doc_type=docType, doc_date=docDate, upload_id=uploadId)
    except rag.UnsupportedFile as e:
        raise HTTPException(415, str(e))
    except rag.UnreadableFile as e:
        raise HTTPException(422, str(e))
    if doc.id in known:
        response.status_code = 200
    if doc.status != 'ready':
        background.add_task(rag.embed_in_background, doc.id)
    return rag.info(doc, len(doc.chunks))


@router.post('/reindex', response_model=Reindexed, summary='Compute the embeddings of every document again, with the current model')
def reindex(store: Store = StoreDep):
    """Needed after the embedding model changes (a key was added or removed): vectors of two models cannot be compared."""
    try:
        chunks = rag.embed(store.db)
        return Reindexed(documents=len(rag.documents(store.db)), chunks=chunks, model=rag.get_embedder().name)
    except EmbeddingError as e:
        raise _unavailable(e)


@router.delete('/documents/{document_id}', status_code=204, summary='Remove a document and its embeddings')
def delete_document(document_id: str, store: Store = StoreDep):
    if not rag.delete_document(store.db, document_id):
        raise HTTPException(404, f'Document {document_id!r} not found')
    return Response(status_code=204)
