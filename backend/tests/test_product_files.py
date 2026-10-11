"""A file about a product is uploaded: it is stored, indexed for search in the same step, and the assistant answers from it."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent import router
from app.main import app

client = TestClient(app)
SHEET = (b'Product,Property,Value,Unit\n'
         b'Phosfusion 80-20,Sulphur per t of product,0.12,t/t\n'
         b'Phosfusion 80-20,P2O5 content,21.5,%\n'
         b'Phosfusion 80-20,Carbon footprint,0.45,t CO2/t\n'
         b'Phosfusion 80-20,Trial date,2026-10-06,\n')
NOTE = b'# Phosfusion 80-20\n\nPhosfusion 80-20 is a pilot grade. It uses 0.12 t of sulphur per tonne and holds 21.5 % P2O5.\n'


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def upload(name: str, data: bytes):
    return client.post('/api/uploads', files={'file': (name, data)})


def say(text: str, **body):
    sim = client.post('/api/simulations', json={'title': 'File'}).json()['id']
    r = client.post(f'/api/simulations/{sim}/messages', json={'text': text, **body})
    return [e for e in (json.loads(line[5:]) for line in r.text.splitlines() if line.startswith('data:')) if e['type'] != 'job']


def test_an_uploaded_product_sheet_is_stored_and_indexed_in_one_step():
    found = client.post('/api/uploads/detect', files={'file': ('product-sheet-phosfusion-80-20.csv', SHEET)}).json()
    # It is not price, freight, trial or crop data: it is a document, and it is said to feed no calculation.
    assert (found['type'], found['typeLabel'], found['affects'], found['problems']) == ('other', 'Document', ['Assistant answers (document search)'], [])
    saved = upload('product-sheet-phosfusion-80-20.csv', SHEET)
    assert saved.status_code == 201 and saved.json()['type'] == 'other' and saved.json()['documentId']
    # In the uploads table, and in the knowledge base without a second request.
    assert saved.json()['id'] in [u['id'] for u in client.get('/api/uploads').json()]
    doc = next(d for d in client.get('/api/knowledge/documents').json() if d['id'] == saved.json()['documentId'])
    assert (doc['name'], doc['uploadId'], doc['status']) == ('product-sheet-phosfusion-80-20.csv', saved.json()['id'], 'ready')
    hit = client.post('/api/knowledge/search', json={'query': 'Phosfusion 80-20 sulphur per t of product', 'limit': 1}).json()['results'][0]
    assert hit['source'] == 'product-sheet-phosfusion-80-20.csv' and '0.12' in hit['passage']
    # What it does not do: the product library is unchanged, and the freshness of the price data too.
    assert not any('80-20' in p['name'] for p in client.get('/api/products').json())
    assert client.get('/api/uploads/freshness').json()['d1'] is not None


@pytest.mark.parametrize('name', ['phosfusion-80-20.md', 'phosfusion-80-20.txt'])
def test_a_text_document_can_be_uploaded_too(name):
    saved = upload(name, NOTE)
    assert saved.status_code == 201 and saved.json()['type'] == 'other' and saved.json()['detail'].endswith('of text')
    assert upload(name, NOTE).json()['duplicate']  # the same file again is the same upload
    assert len([d for d in client.get('/api/knowledge/documents').json() if d['name'] == name]) == 1


def test_a_data_file_keeps_its_type():
    quotes = b'Product,Date,Low USD/t,High USD/t\nDAP,2026-09-28,815,850\n'
    assert upload('quotes.csv', quotes).json()['type'] == 'prices'
    assert upload('routes.csv', b'Route,Week ending,USD/t\nJorf-Santos,2026-10-01,25.5\n').json()['type'] == 'freight'


def test_the_rule_based_assistant_answers_about_a_product_from_its_file():
    upload('product-sheet-phosfusion-80-20.csv', SHEET)
    events = say('give me information about product Phosfusion 80-20', mode='script')
    texts = [e['payload']['content'] for e in events if e['type'] == 'text']
    assert texts[0].startswith('That product is not in the product library')
    assert '**Phosfusion 65-35** (phosfusion)' not in ' '.join(texts)  # not the card of another grade
    assert 'Sulphur per t of product' in texts[1] and '0.12' in texts[1]
    assert [e['payload']['source'] for e in events if e['type'] == 'citation'][0] == 'product-sheet-phosfusion-80-20.csv'
    # A product the library has is still answered from the library, and a question about the documents from the documents.
    assert say('give me information about product TSP', mode='script')[0]['payload']['content'].startswith('**TSP** (reference)')
    asked = say('What do the documents say about Phosfusion 65-35?', mode='script')
    assert [e['type'] for e in asked][:2] == ['step', 'tool'] and not any(e['payload'].get('content', '').startswith('**Phosfusion 65-35**') for e in asked if e['type'] == 'text')


def _reply(message: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {'choices': [{'message': {'role': 'assistant', **message}, 'finish_reason': 'stop'}]}
    return m


def _lookup(product: str) -> MagicMock:
    return _reply({'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'get_product', 'arguments': json.dumps({'product': product})}}]})


def ask_model(text: str, replies: list):
    router.record_llm_success()
    router._turns.clear()
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key', 'LLM_ENABLED': 'true'}), patch('httpx.AsyncClient.post', side_effect=replies) as post:
        return say(text), post


def test_the_model_is_given_the_file_when_the_library_does_not_have_the_product():
    upload('product-sheet-phosfusion-80-20.csv', SHEET)
    answer = 'Phosfusion 80-20 is not in the product library. Its product sheet gives 0.12 t/t of sulphur and 21.5 % P2O5 [K1].'
    events, post = ask_model('give me information about product Phosfusion 80-20', [_lookup('Phosfusion 80-20'), _reply({'content': answer})])
    given = json.loads(post.call_args_list[1].kwargs['json']['messages'][-1]['content'])  # what the tool returned to the model
    assert given['note'].startswith("No product named 'Phosfusion 80-20'") and given['results'][0]['source'] == 'product-sheet-phosfusion-80-20.csv'
    assert [e['payload']['source'] for e in events if e['type'] == 'citation'] == ['product-sheet-phosfusion-80-20.csv']
    assert next(e for e in events if e['type'] == 'text')['payload']['content'].startswith('Phosfusion 80-20 is not in the product library.')


def test_an_answer_with_nothing_behind_it_says_so():
    invented = _reply({'content': 'Phosfusion 99-1 costs 123.45 USD/t.'})
    events, _ = ask_model('give me information about product Phosfusion 99-1', [_reply({'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'list_products', 'arguments': '{}'}}]}), invented, invented])
    text = next(e for e in events if e['type'] == 'text')['payload']['content']
    assert text == 'I could not find that in the product library or in the uploaded documents, so I have nothing reliable to tell you about it.'
