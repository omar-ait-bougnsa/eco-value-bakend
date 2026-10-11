"""The /api/knowledge endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
NOTE = b'# Carbon valuation methodology\n\n## Baseline\n\nThe baseline carbon price for Scope 1 to 3 emissions is reviewed every quarter.\n'


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def documents() -> dict[str, dict]:
    return {d['name']: d for d in client.get('/api/knowledge/documents').json()}


def test_reset_loads_the_documents_that_ship_with_the_backend():
    docs = documents()
    assert len(docs) == 7 and all(d['status'] == 'ready' and d['seeded'] for d in docs.values())
    assert docs['engine.md']['type'] == 'methodology' and docs['engine.md']['pages'] is None
    assert docs['argus-fob-morocco-30-09-2026.xlsx'] | {'id': ''} == {
        'id': '', 'name': 'argus-fob-morocco-30-09-2026.xlsx', 'title': 'argus-fob-morocco-30-09-2026.xlsx', 'type': 'market_report',
        'date': '2026-09-30', 'pages': None, 'chunks': 1, 'status': 'ready', 'error': None, 'uploadId': None, 'seeded': True,
    }


def test_search():
    r = client.post('/api/knowledge/search', json={'query': 'freight rate from Jorf Lasfar to Santos', 'limit': 2})
    assert r.status_code == 200
    body = r.json()
    assert body['model'] == 'hash-1536' and len(body['results']) == 2
    top = body['results'][0]
    assert set(top) == {'passage', 'source', 'date', 'page', 'pageEnd', 'section', 'docType', 'relevanceScore', 'documentId', 'chunkId'}
    assert (top['source'], top['date'], top['section'], top['docType']) == ('fertilizer-week-historical-freights-01-10-2026.xlsx', '2026-10-01', 'Phosphates', 'freight')

    only = client.post('/api/knowledge/search', json={'query': 'freight Jorf Lasfar Santos', 'docType': 'agronomy'}).json()
    assert only['results'] == []
    for bad in ({'query': ''}, {'query': 'x', 'limit': 0}, {'query': 'x', 'docType': 'gossip'}, {}):
        assert client.post('/api/knowledge/search', json=bad).status_code == 400


def test_a_document_is_indexed_found_and_removed():
    r = client.post('/api/knowledge/documents', files={'file': ('carbon-note-2026-09-01.md', NOTE)})
    assert r.status_code == 201
    doc = r.json()
    assert (doc['title'], doc['type'], doc['date'], doc['chunks'], doc['seeded']) == ('Carbon valuation methodology', 'methodology', '2026-09-01', 1, False)
    assert doc['status'] == 'indexing'  # the embeddings are computed after the response…
    assert documents()['carbon-note-2026-09-01.md']['status'] == 'ready'  # …and are there by now

    top = client.post('/api/knowledge/search', json={'query': 'baseline carbon price Scope emissions'}).json()['results'][0]
    assert (top['documentId'], top['source'], top['section']) == (doc['id'], 'Carbon valuation methodology', 'Baseline')

    # The kind is read from the title and headings too: this file's name and body say nothing about methodology.
    policy = client.post('/api/knowledge/documents', files={'file': ('note.md', b'# Value sharing policy\n\nThe share of the agronomic value kept by the producer.\n')}).json()
    assert policy['type'] == 'methodology'
    client.delete(f'/api/knowledge/documents/{policy["id"]}')

    again = client.post('/api/knowledge/documents', files={'file': ('copy.md', NOTE)})
    assert again.status_code == 200 and again.json()['id'] == doc['id'] and again.json()['status'] == 'ready'
    assert len(documents()) == 8

    assert client.delete(f'/api/knowledge/documents/{doc["id"]}').status_code == 204
    assert 'carbon-note-2026-09-01.md' not in documents()
    assert all(r['documentId'] != doc['id'] for r in client.post('/api/knowledge/search', json={'query': 'baseline carbon price Scope emissions', 'limit': 20}).json()['results'])
    assert client.delete(f'/api/knowledge/documents/{doc["id"]}').status_code == 404


def test_the_fields_of_the_form_override_what_is_detected():
    upload = client.get('/api/uploads').json()[0]
    r = client.post('/api/knowledge/documents', files={'file': ('note.txt', b'Rates for supramax vessels eased.')},
                    data={'title': 'CRU Fertilizer Week', 'docType': 'freight', 'docDate': '2026-09-24', 'uploadId': upload['id']})
    assert r.status_code == 201
    assert r.json() | {'id': ''} == {'id': '', 'name': 'note.txt', 'title': 'CRU Fertilizer Week', 'type': 'freight', 'date': '2026-09-24', 'pages': None,
                                     'chunks': 1, 'status': 'indexing', 'error': None, 'uploadId': upload['id'], 'seeded': False}


@pytest.mark.parametrize('name, data, form, status, says', [
    ('prices.xls', b'\xd0\xcf\x11\xe0', {}, 415, 'save the file as .xlsx'),
    ('archive.zip', b'PK', {}, 415, 'Only .pdf'),
    ('broken.pdf', b'not a pdf', {}, 400, 'could not be read'),
    ('empty.txt', b'   ', {}, 400, 'No text found'),
    ('note.txt', b'Some text.', {'uploadId': 'u-missing'}, 404, "Upload 'u-missing' not found"),
])
def test_files_that_are_refused(name, data, form, status, says):
    r = client.post('/api/knowledge/documents', files={'file': (name, data)}, data=form)
    assert r.status_code == status and says in r.json()['detail']
    assert len(documents()) == 7


def test_a_file_over_20_mb_is_refused():
    r = client.post('/api/knowledge/documents', files={'file': ('big.txt', b'a' * (20 * 1024 * 1024 + 1))})
    assert r.status_code == 413


def test_reindex_and_reset():
    client.post('/api/knowledge/documents', files={'file': ('carbon-note.md', NOTE)})
    chunks = sum(d['chunks'] for d in documents().values())
    assert client.post('/api/knowledge/reindex').json() == {'documents': 8, 'chunks': chunks, 'model': 'hash-1536'}
    client.post('/api/reset')
    assert len(documents()) == 7 and 'carbon-note.md' not in documents()
