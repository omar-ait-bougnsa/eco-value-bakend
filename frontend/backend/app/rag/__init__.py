"""Knowledge base for the agent: narrative documents in a vector store, searched by meaning (RAG.md).

Exact numbers stay in the relational tables and go through the engine. This package holds what explains them.
"""
from .embeddings import EmbeddingError, get_embedder
from .index import DocumentInfo, Passage, add_document, delete_document, documents, embed, embed_in_background, info, prepare, search
from .parser import SUPPORTED, DocType, UnreadableFile, UnsupportedFile

__all__ = [
    'DocType', 'DocumentInfo', 'EmbeddingError', 'Passage', 'SUPPORTED', 'UnreadableFile', 'UnsupportedFile',
    'add_document', 'delete_document', 'documents', 'embed', 'embed_in_background', 'get_embedder', 'info', 'prepare', 'search',
]
