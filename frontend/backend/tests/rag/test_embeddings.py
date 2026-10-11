"""Embedding models: the offline one, the cloud one (network mocked), and which one is picked."""
import math
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.db import EMBEDDING_DIM
from app.rag.embeddings import CloudEmbedder, EmbeddingError, HashEmbedder, get_embedder, pad

cosine = lambda a, b: sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b)))


def test_hash_embeddings_are_stable_unit_vectors_that_put_shared_words_together():
    e = HashEmbedder()
    freight, same, close, far = e.embed([
        'Freight rate from Jorf Lasfar to Santos', 'Freight rate from Jorf Lasfar to Santos',
        'Jorf Lasfar – Santos freight rates eased', 'Yield gain of maize in field trials',
    ])
    assert freight == same and len(freight) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in freight)), 1)
    assert cosine(freight, close) > 0.3 > 0.05 > abs(cosine(freight, far))
    assert not any(e.embed(['the of and'])[0])  # nothing but stop words


def test_padding_leaves_cosine_similarity_unchanged():
    a, b = [0.2, -0.5, 0.8], [0.9, 0.1, -0.3]
    assert len(pad(a)) == EMBEDDING_DIM
    assert math.isclose(cosine(pad(a), pad(b)), cosine(a, b))
    with pytest.raises(EmbeddingError, match='dimensions'):
        pad([0.0] * (EMBEDDING_DIM + 1))


def _reply(inputs: list[str]) -> MagicMock:
    # The API may answer out of order: each item says which input it is for.
    data = [{'index': i, 'embedding': [float(len(text)), float(i)]} for i, text in enumerate(inputs)]
    return MagicMock(json=lambda: {'data': data[::-1]}, raise_for_status=lambda: None)


def test_cloud_embeddings_are_asked_in_batches_and_returned_in_order():
    texts = ['x' * (i % 7 + 1) for i in range(150)]
    with patch('httpx.post', side_effect=lambda url, **kw: _reply(kw['json']['input'])) as post:
        vectors = CloudEmbedder('https://openrouter.ai/api/v1/embeddings', 'key', 'openai/text-embedding-3-small').embed(texts)
    assert [len(c.kwargs['json']['input']) for c in post.call_args_list] == [64, 64, 22]
    assert post.call_args.kwargs['headers'] == {'Authorization': 'Bearer key'}
    assert post.call_args.kwargs['json']['model'] == 'openai/text-embedding-3-small'
    assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


@pytest.mark.parametrize('failure', [
    httpx.ConnectError('no route to host'),
    lambda url, **kw: MagicMock(raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError('401', request=MagicMock(), response=MagicMock()))),
    lambda url, **kw: MagicMock(json=lambda: {'error': 'no data'}, raise_for_status=lambda: None),
    lambda url, **kw: MagicMock(json=lambda: {'data': []}, raise_for_status=lambda: None),
])
def test_a_failed_cloud_request_is_an_embedding_error(failure):
    with patch('httpx.post', side_effect=failure), pytest.raises(EmbeddingError):
        CloudEmbedder('https://api.openai.com/v1/embeddings', 'key', 'text-embedding-3-small').embed(['a'])


def _env(monkeypatch, **values):
    # An empty key stops the lookup in .env files, so the test does not depend on the machine it runs on.
    for name, value in {'EMBEDDINGS': 'auto', 'LLM_ENABLED': 'true', 'OPENAI_API_KEY': '', 'OPENROUTER_API_KEY': '', 'openrouter_api_key': '', **values}.items():
        monkeypatch.setenv(name, value)


def test_which_model_is_used(monkeypatch):
    _env(monkeypatch)
    with patch('app.rag.embeddings._has_fastembed', return_value=False):
        assert get_embedder().name == f'hash-{EMBEDDING_DIM}'
    with patch('app.rag.embeddings._has_fastembed', return_value=True):
        assert get_embedder().name == 'all-MiniLM-L6-v2'

    _env(monkeypatch, OPENROUTER_API_KEY='or-key')
    router = get_embedder()
    assert (router.url, router.model, router.name) == ('https://openrouter.ai/api/v1/embeddings', 'openai/text-embedding-3-small', 'text-embedding-3-small')

    _env(monkeypatch, OPENROUTER_API_KEY='or-key', OPENAI_API_KEY='oa-key')
    openai = get_embedder()
    assert (openai.url, openai.model, openai.key) == ('https://api.openai.com/v1/embeddings', 'text-embedding-3-small', 'oa-key')
    assert openai.name == router.name  # the same model: its vectors are comparable through either provider

    _env(monkeypatch, OPENROUTER_API_KEY='or-key', LLM_ENABLED='false')  # the offline switch of the agent holds here too
    with patch('app.rag.embeddings._has_fastembed', return_value=False):
        assert isinstance(get_embedder(), HashEmbedder)

    _env(monkeypatch, OPENROUTER_API_KEY='or-key', EMBEDDINGS='hash')
    assert isinstance(get_embedder(), HashEmbedder)


@pytest.mark.parametrize('setting, says', [('cloud', 'needs OPENAI_API_KEY'), ('local', 'needs the fastembed package'), ('fastest', 'expected auto, cloud, local or hash')])
def test_a_setting_that_cannot_work_says_why(monkeypatch, setting, says):
    _env(monkeypatch, EMBEDDINGS=setting)
    with patch('app.rag.embeddings._has_fastembed', return_value=False), pytest.raises(EmbeddingError, match=says):
        get_embedder()
