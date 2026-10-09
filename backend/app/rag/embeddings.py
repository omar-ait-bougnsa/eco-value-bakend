"""Embeddings for the knowledge base (RAG.md §3.2).

`EMBEDDINGS` picks the model:
- `cloud`: text-embedding-3-small through OpenAI (`OPENAI_API_KEY`) or OpenRouter (the agent's key).
- `local`: all-MiniLM-L6-v2 on this machine with `fastembed` (an optional install; it downloads the model once).
- `hash`:  word hashing. No model and no network: it matches on shared words, not on meaning.
- `auto` (default): cloud when there is a key and `LLM_ENABLED` is not false, else local when fastembed is installed, else hash.
"""
import hashlib
import math
import os
import re
from functools import lru_cache
from typing import Protocol

import httpx

from ..db import EMBEDDING_DIM

BATCH = 64
TIMEOUT_SECONDS = 30.0


class EmbeddingError(RuntimeError):
    """The model could not be reached or refused the request."""


class Embedder(Protocol):
    name: str  # stored with every vector: a search only reads the vectors of its own model
    min_score: float  # cosine similarity under which a passage has nothing to do with the question, on this model's scale

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def pad(vector: list[float]) -> list[float]:
    """The vector at the width of the database column. Zeros on the right leave cosine similarity unchanged."""
    if len(vector) > EMBEDDING_DIM:
        raise EmbeddingError(f'The embedding has {len(vector)} dimensions; the column holds {EMBEDDING_DIM}')
    return [float(x) for x in vector] + [0.0] * (EMBEDDING_DIM - len(vector))


# ───────────────────────── hash ─────────────────────────

_WORD = re.compile(r'[^\W_]+(?:\.\d+)?')
_STOP = frozenset(
    'a an and are as at be by for from has have how in is it its of on or that the this to was were what when where which who why will with '
    'about according any do does explain give me say tell '
    'au aux ce ces dans de des du en est et il la le les ou par pour que qui sur un une'.split()
)


class HashEmbedder:
    """Counts of words and word pairs, each hashed to one of `dim` positions (the "hashing trick").

    As wide as the column: the wider the vector, the fewer unrelated words land on the same position.
    """
    dim = EMBEDDING_DIM
    name = f'hash-{EMBEDDING_DIM}'
    min_score = 0.1  # on the documents that ship: off-topic questions stay under 0.07, questions they answer start at 0.13

    def _features(self, text: str) -> dict[str, float]:
        words = [w[:-1] if len(w) > 3 and w.endswith('s') else w for w in _WORD.findall(text.lower()) if w not in _STOP]
        counts: dict[str, float] = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        for a, b in zip(words, words[1:]):
            counts[f'{a} {b}'] = counts.get(f'{a} {b}', 0) + 0.5
        return counts

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for feature, count in self._features(text).items():
            h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), 'big')
            vector[h % self.dim] += (1 if h >> 63 else -1) * (1 + math.log(count + 1))
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]


# ───────────────────────── cloud ─────────────────────────

class CloudEmbedder:
    min_score = 0.2  # not measured against the live model (no key at the time of writing): tune it with real documents

    def __init__(self, url: str, key: str, model: str) -> None:
        self.url, self.key, self.model = url, key, model
        self.name = model.split('/')[-1]  # the same model through either provider gives comparable vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            try:
                r = httpx.post(self.url, headers={'Authorization': f'Bearer {self.key}'}, json={'model': self.model, 'input': texts[i:i + BATCH]}, timeout=TIMEOUT_SECONDS)
                r.raise_for_status()
                data = sorted(r.json()['data'], key=lambda d: d['index'])
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
                raise EmbeddingError(f'Embedding request to {httpx.URL(self.url).host} failed: {e}') from e
            if len(data) != len(texts[i:i + BATCH]):
                raise EmbeddingError(f'Asked for {len(texts[i:i + BATCH])} embeddings, received {len(data)}')
            vectors += [d['embedding'] for d in data]
        return vectors


# ───────────────────────── local ─────────────────────────

@lru_cache(maxsize=1)
def _minilm():
    from fastembed import TextEmbedding
    return TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')


class LocalEmbedder:
    name = 'all-MiniLM-L6-v2'
    min_score = 0.25  # on the documents that ship: off-topic questions stay under 0.23, questions they answer start at 0.26

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return [[float(x) for x in v] for v in _minilm().embed(texts)]
        except Exception as e:  # fastembed surfaces download and ONNX runtime errors of several kinds
            raise EmbeddingError(f'Local embedding model failed: {e}') from e


def _has_fastembed() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def _cloud() -> CloudEmbedder | None:
    from ..agent.router import get_openrouter_api_key  # here, not at the top: app.agent imports this package for its search tool
    model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    if key := os.getenv('OPENAI_API_KEY', '').strip():
        return CloudEmbedder('https://api.openai.com/v1/embeddings', key, model)
    if key := get_openrouter_api_key():
        return CloudEmbedder('https://openrouter.ai/api/v1/embeddings', key, model if '/' in model else f'openai/{model}')
    return None


def get_embedder() -> Embedder:
    choice = os.getenv('EMBEDDINGS', 'auto').lower()
    if choice == 'hash':
        return HashEmbedder()
    if choice == 'local':
        if not _has_fastembed():
            raise EmbeddingError('EMBEDDINGS=local needs the fastembed package: pip install fastembed')
        return LocalEmbedder()
    if choice == 'cloud':
        if (cloud := _cloud()) is None:
            raise EmbeddingError('EMBEDDINGS=cloud needs OPENAI_API_KEY or an OpenRouter key')
        return cloud
    if choice != 'auto':
        raise EmbeddingError(f'EMBEDDINGS={choice!r}: expected auto, cloud, local or hash')
    enabled = os.getenv('LLM_ENABLED', 'true').lower() in ('true', '1', 'yes')
    return (enabled and _cloud()) or (LocalEmbedder() if _has_fastembed() else HashEmbedder())
