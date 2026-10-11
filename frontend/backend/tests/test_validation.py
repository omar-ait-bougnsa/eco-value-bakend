"""Validation rules, record review, upload ingestion and the cost contract (limits.py, maintenance.py, routers)."""
import json
import pathlib
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app import maintenance, migrations
from app.agent.tools import validate_tool_call
from app.data import seed
from app.db import ProductRow, UploadRow
from app.limits import Limits, get_limits, product_errors, run_input_errors, yield_errors
from app.main import app

client = TestClient(app)
SAMPLES = pathlib.Path(__file__).parent.parent / 'sample-uploads'
GOOD = {'name': 'Phosfusion 70-30', 'recipe': {'rockDry': 0.7, 'sulphur': 0.1}, 'composition': {'P2O5': 0.24}}
# The two records found in the running app.
BAD_RECIPE = {'name': 'Phosfusion 50-51', 'recipe': {'rockDry': 65, 'rockWet': 50, 'sulphur': 760}, 'composition': {'P2O5': 0.2}}
BAD_NAME = {'name': 'ffffffff', 'recipe': {'rockDry': 3, 'rockWet': 20, 'sulphur': 20}, 'composition': {}, 'pcf': 65}


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def fields(resp):
    return {e['field']: e['message'] for e in resp.json()['errors']}


# ───────────────────────── rules ─────────────────────────

def test_the_demo_products_pass_the_rules():
    assert [product_errors(p.model_dump()) for p in seed.products()] == [[]] * 12


def test_the_two_bad_records_are_named_field_by_field():
    e = dict(product_errors(BAD_RECIPE))
    assert e == {'recipe.rockDry': 'must be between 0 and 3 t/t', 'recipe.rockWet': 'must be between 0 and 3 t/t', 'recipe.sulphur': 'must be between 0 and 3 t/t',
                 'recipe': 'uses 875 t of ingredients per t of product: at most 4 t/t'}
    e = dict(product_errors(BAD_NAME))
    assert e['name'] == 'is not a name: one character repeated' and e['pcf'] == 'must be between 0 and 10 t CO₂/t' and 'recipe.sulphur' in e


@pytest.mark.parametrize('change, field', [
    ({'name': '  '}, 'name'), ({'name': '12345'}, 'name'), ({'recipe': {}}, 'recipe'), ({'recipe': {'sulphur': float('nan')}}, 'recipe.sulphur'),
    ({'composition': {'N': 0.6, 'P2O5': 0.6}}, 'composition'), ({'composition': {'N': 1.2}}, 'composition.N'),
    ({'pcf': -1}, 'pcf'), ({'appRate': 0}, 'appRate'), ({'yieldGain': 30}, 'yieldGain'),
    ({'yieldGain': 12, 'yieldGainUnit': '%'}, 'baselineYield'), ({'yieldGain': 120, 'yieldGainUnit': '%', 'baselineYield': 6}, 'yieldGain'),
])
def test_product_rules(change, field):
    assert field in dict(product_errors({**GOOD, **change}))


def test_limits_are_configuration(monkeypatch):
    monkeypatch.setenv('EVS_LIMITS', json.dumps({'recipeQtyMax': 100, 'recipeTotalMax': 1000}))
    get_limits.cache_clear()
    try:
        assert get_limits().recipeQtyMax == 100
        assert 'recipe.rockDry' not in dict(product_errors(BAD_RECIPE)) and 'recipe.sulphur' in dict(product_errors(BAD_RECIPE))
    finally:
        monkeypatch.delenv('EVS_LIMITS')
        get_limits.cache_clear()
    assert client.get('/api/limits').json() == Limits().model_dump()


def test_a_yield_gain_is_a_quantity_with_a_unit():
    L = Limits()
    assert yield_errors(0.12, 't/ha', None, L) == [] and yield_errors(12, '%', 4.0, L) == []
    assert dict(yield_errors(12, '%', None, L)) == {'baselineYield': 'is required to turn a yield gain in % into t/ha'}
    base = client.post('/api/engine/run', json={}).json()
    assert base['input']['yieldGainUnit'] == 't/ha' and base['output']['perProduct']['phos-65-35']['yieldGainTHa'] == 0.12
    # 3 % of 4 t/ha is the same 0.12 t/ha: the same value pricing.
    pct = client.post('/api/engine/run', json={'yieldGain': 3, 'yieldGainUnit': '%', 'baselineYield': 4}).json()['output']['perProduct']['phos-65-35']
    assert pct['yieldGainTHa'] == pytest.approx(0.12) and pct['prices']['value'] == pytest.approx(base['output']['perProduct']['phos-65-35']['prices']['value'])
    assert fields(client.post('/api/engine/run', json={'yieldGain': 3, 'yieldGainUnit': '%'})) == {'baselineYield': 'is required to turn a yield gain in % into t/ha'}


def test_the_unit_flag_stays_until_the_product_stores_its_unit():
    codes = lambda: {f['code']: f for f in client.post('/api/engine/run', json={}).json()['output']['flags']}
    assert codes()['U1']['title'] == 'Yield gain has no stored unit — 0.12 is used as t/ha'
    product = client.get('/api/products/phos-65-35').json()
    assert client.put('/api/products/phos-65-35', json={**product, 'yieldGainUnit': 't/ha'}).status_code == 200  # as read, plus the unit
    assert 'U1' not in codes()


def test_run_input_rules():
    ok = client.post('/api/engine/run', json={}).json()['input']
    assert run_input_errors(ok, 2026) == []
    bad = dict(run_input_errors({**ok, 'costPlusMargin': 9, 'cropPrice': 1e9, 'appRateNew': 0, 'methods': [], 'rampTargetYear': 1990}, 2026))
    assert set(bad) == {'costPlusMargin', 'cropPrice', 'appRateNew', 'methods', 'rampTargetYear'}
    assert fields(client.post('/api/engine/validate', json={'costPlusMargin': 9})) == {'costPlusMargin': 'must be between 0 and 2 (fraction)'}
    assert client.post('/api/engine/validate', json={}).json() == {'errors': []}


# ───────────────────────── products API ─────────────────────────

def test_invalid_products_are_refused_with_one_error_per_field():
    r = client.post('/api/products', json=BAD_RECIPE)
    assert r.status_code == 400 and set(fields(r)) == {'recipe.rockDry', 'recipe.rockWet', 'recipe.sulphur', 'recipe'}
    assert r.json()['detail'].startswith('recipe.rockDry: must be between 0 and 3 t/t; ')
    assert set(fields(client.post('/api/products', json=BAD_NAME))) >= {'name', 'pcf', 'recipe.sulphur'}
    assert fields(client.post('/api/products', json={**GOOD, 'recipe': {'sulphur': '0.1kg'}}))['recipe.sulphur'].startswith('Input should be a valid number')
    nan = client.post('/api/products', content='{"name": "Nan product", "recipe": {"sulphur": NaN}}', headers={'content-type': 'application/json'})
    assert nan.status_code == 400 and 'recipe.sulphur' in fields(nan)
    assert 'name' in fields(client.post('/api/products', json={'recipe': {'sulphur': 0.1}}))
    assert len(client.get('/api/products').json()) == 12  # nothing was saved


def test_valid_products_are_saved_and_names_are_unique():
    created = client.post('/api/products', json={**GOOD, 'name': '  Phosfusion 70-30  '})
    assert created.status_code == 201 and created.json()['name'] == 'Phosfusion 70-30' and created.json()['status'] == 'active'
    assert fields(client.post('/api/products', json={**GOOD, 'name': 'phosfusion 70-30'})) == {'name': 'is already the name of another product (phosfusion-70-30)'}  # whatever the case
    assert fields(client.put('/api/products/phos-50-50', json={**GOOD, 'name': 'TSP'})) == {'name': 'is already the name of another product (TSP)'}
    assert client.post('/api/products/validate', json=BAD_RECIPE).json()['errors'][0] == {'field': 'recipe.rockDry', 'message': 'must be between 0 and 3 t/t'}
    assert client.post('/api/products/validate', params={'id': 'phosfusion-70-30'}, json=GOOD).json() == {'errors': []}


def test_list_editor_and_engine_agree_on_the_cost_of_phosfusion_65_35():
    product = client.get('/api/products/phos-65-35').json()
    listed = client.get('/api/products/phos-65-35/cost').json()
    editor = client.post('/api/products/recipe-cost', json={'recipe': product['recipe']}).json()
    engine = client.post('/api/engine/run', json={'productIds': ['phos-65-35']}).json()['output']['perProduct']['phos-65-35']
    assert listed == editor
    assert listed['rawMaterial'] == engine['rawMaterial'] == pytest.approx(310.90, abs=0.005)
    assert [(l['id'], l['price'], l['usd']) for l in editor['lines']] == [(l['id'], l['price'], l['usd']) for l in engine['lines']]
    assert editor['lines'][-1] == {'id': 'sulphur', 'label': 'Sulphur', 'qty': 0.15993, 'price': 900, 'usd': pytest.approx(143.937)}
    # Where the prices come from, and for which days.
    assert (editor['periodFrom'], editor['periodTo'], editor['asOf']) == ('2026-01-01', '2026-10-02', '2026-10-02') and editor['source'].startswith('Standard cost 2026')
    # Another period: still the same in the list, the editor and the engine.
    span = {'periodFrom': '2024-01-01', 'periodTo': '2024-12-31'}
    y = client.get('/api/products/phos-65-35/cost', params=span).json()['rawMaterial']
    assert y == client.post('/api/products/recipe-cost', json={'recipe': product['recipe'], **span}).json()['rawMaterial']
    assert y == client.post('/api/engine/run', json=span).json()['output']['perProduct']['phos-65-35']['rawMaterial']


def test_no_total_is_shown_as_zero():
    empty = client.post('/api/products/recipe-cost', json={'recipe': {'sulphur': 0}}).json()
    assert empty['rawMaterial'] is None and empty['unavailable'] == 'The recipe has no ingredient with a quantity'


# ───────────────────────── uploads ─────────────────────────

def sample(name='argus-fob-morocco-30-09-2026.xlsx'):
    return {'file': (name, (SAMPLES / name).read_bytes())}


def test_an_upload_is_made_from_the_file_and_only_once():
    first = client.post('/api/uploads', files=sample())
    assert first.status_code == 201
    saved = first.json()
    assert saved['name'] == 'argus-fob-morocco-30-09-2026.xlsx' and saved['type'] == 'prices' and saved['dataThrough'] == '2026-09-30'
    assert len(saved['contentHash']) == 64 and saved['sizeBytes'] > 0 and saved['detail'] == '3 rows · 1 sheet: FOB Morocco'
    again = client.post('/api/uploads', files=sample())  # the same bytes: the same upload
    assert again.status_code == 200 and again.json()['id'] == saved['id'] and again.json()['duplicate']
    renamed = client.post('/api/uploads', files={'file': ('copy.xlsx', (SAMPLES / 'argus-fob-morocco-30-09-2026.xlsx').read_bytes())})
    assert renamed.status_code == 200 and renamed.json()['id'] == saved['id']
    assert len(client.get('/api/uploads').json()) == 6
    assert client.post('/api/uploads/detect', files=sample()).json()['duplicateOf'] == saved['id']
    assert client.get('/api/audit').json()[0]['action'] == 'duplicate-upload'


@pytest.mark.parametrize('name, data, message', [
    ('prices.xlsx', b'not a workbook', 'could not be read as a .xlsx file'),
    ('prices.csv', b'', 'is empty'),
    ('prices.csv', b'   \n', 'could not be read as a .csv file'),
    ('photo.png', b'hello', 'only .xlsx, .csv, .pdf, .docx, .txt, .md files are accepted'),
    ('legacy.xls', b'\xd0\xcf\x11\xe0', 'save the workbook as .xlsx'),
    ('.csv', b'a,b\n1,2\n', 'has no file name'),
])
def test_malformed_uploads_are_refused(name, data, message):
    r = client.post('/api/uploads', files={'file': (name, data)})
    assert r.status_code == 400 and message in fields(r)['file']
    assert len(client.get('/api/uploads').json()) == 5
    assert client.post('/api/uploads', json={'name': 'string', 'type': 'prices', 'fileDate': '2026-10-01', 'dataThrough': '2026-10-01'}).status_code == 400  # metadata without a file


# ───────────────────────── stored records ─────────────────────────

def _bad_rows(store):
    """What the running app held: two unusable products, two uploads named "string" and a duplicated file."""
    for i, p in enumerate((BAD_RECIPE, BAD_NAME)):
        store.db.add(ProductRow(id=f'bad-{i}', position=100 + i, family='phosfusion', pcfPlaceholder=None, appRate=None, yieldGain=None,
                                **{'pcf': None, **p, 'composition': {'N': 0, 'P2O5': 0, 'K2O': 0, 'S': 0}}))
    day = date(2026, 10, 5)
    for i, name in enumerate(('string', 'string', 'argus-fob-morocco-30-09-2026.xlsx', 'argus-fob-morocco-30-09-2026.xlsx')):
        store.db.add(UploadRow(id=f'x{i}', createdAt=datetime(2026, 10, 5, 10, i, tzinfo=timezone.utc), name=name, type='prices', uploadedAt=day, fileDate=day, dataThrough=day))
    store.db.commit()


def test_review_quarantines_bad_records_without_deleting_them(store):
    _bad_rows(store)
    assert client.get('/api/products/bad-0/cost').json()['rawMaterial'] == pytest.approx(697_800)  # the cost the list showed
    found = maintenance.review(store)
    assert [(e, i) for e, i, _, _ in found] == [('product', 'bad-0'), ('product', 'bad-1'), ('upload', 'x0'), ('upload', 'x1'), ('upload', 'x3')]
    assert found[3][3] == ["name: 'string' is not a file name", 'duplicate of x0'] and found[4][3] == ['duplicate of x2']
    assert client.get('/api/products/bad-0').json()['status'] == 'active'  # a report changes nothing

    maintenance.quarantine(store, found)
    kept = client.get('/api/products/bad-0').json()
    assert kept['status'] == 'quarantined' and kept['issues'][0] == 'recipe.rockDry: must be between 0 and 3 t/t' and kept['recipe']['sulphur'] == 760
    assert fields(client.post('/api/engine/run', json={'productIds': ['bad-0']})) == {'productIds': 'bad-0 is quarantined and cannot be priced until it is corrected'}
    assert [u['id'] for u in client.get('/api/uploads').json() if u['id'].startswith('x')] == ['x2']
    assert {u['id'] for u in client.get('/api/uploads', params={'includeQuarantined': True}).json()} >= {'x0', 'x1', 'x2', 'x3'}
    assert [(a['action'], a['entityId']) for a in client.get('/api/audit').json()][::-1] == [('quarantine', i) for i in ('bad-0', 'bad-1', 'x0', 'x1', 'x3')]
    assert maintenance.review(store) == []  # nothing left to set aside

    # Correcting the product restores it.
    assert client.put('/api/products/bad-0', json=GOOD).json()['status'] == 'active'
    assert client.get('/api/audit').json()[0]['action'] == 'restore'
    assert client.post('/api/engine/run', json={'productIds': ['bad-0']}).status_code == 200


def test_migration_adds_the_new_columns_once(tmp_path):
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path / "old.db"}')
    with engine.begin() as conn:  # the tables as an earlier version made them
        conn.execute(text('CREATE TABLE products (id VARCHAR PRIMARY KEY, name VARCHAR, yield_gain FLOAT)'))
        conn.execute(text('CREATE TABLE uploads (id VARCHAR PRIMARY KEY, name VARCHAR)'))
        conn.execute(text("INSERT INTO products VALUES ('p1', 'Kept', 0.12)"))
    assert migrations.upgrade(engine) == ['products.yield_gain_unit', 'products.baseline_yield', 'products.status', 'products.issues',
                                          'uploads.size_bytes', 'uploads.content_hash', 'uploads.status', 'uploads.issues']
    assert migrations.upgrade(engine) == []
    assert {'status', 'issues', 'yield_gain_unit'} <= {c['name'] for c in inspect(engine).get_columns('products')}
    with engine.connect() as conn:
        assert conn.execute(text('SELECT name, yield_gain, status FROM products')).all() == [('Kept', 0.12, None)]


# ───────────────────────── agent ─────────────────────────

def test_status_says_what_answers_and_never_the_key(monkeypatch):
    from app.agent.router import record_llm_success
    record_llm_success()  # no outage left over from another test
    monkeypatch.setenv('LLM_ENABLED', 'false')
    off = client.get('/api/agent/status').json()
    assert (off['mode'], off['fallbackReason'], off['label']) == ('script', 'disabled', 'Rule-based assistant (AI model switched off)')
    monkeypatch.setenv('LLM_ENABLED', 'true')
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    none = client.get('/api/agent/status').json()
    assert (none['mode'], none['configured'], none['model'], none['label']) == ('script', False, None, 'Rule-based assistant (no AI model configured)')
    assert none['capabilities'].startswith('a fixed set of requests')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-secret-value')
    monkeypatch.setenv('OPENROUTER_MODEL', 'anthropic/claude-sonnet-5.5')
    on = client.get('/api/agent/status').json()
    assert (on['mode'], on['provider'], on['model'], on['label']) == ('llm', 'openrouter', 'anthropic/claude-sonnet-5.5', 'AI model connected')
    assert 'sk-or-secret-value' not in json.dumps(on)


def frames_of(resp):
    return [json.loads(line[5:]) for line in resp.text.splitlines() if line.startswith('data:')]


def events_of(resp):
    """The turn's events, without the two `job` frames around them."""
    return [e for e in frames_of(resp) if e['type'] != 'job']


def test_rule_based_assistant_end_to_end():
    sim = client.post('/api/simulations', json={'title': 'Chat'}).json()
    say = lambda text, **extra: events_of(client.post(f'/api/simulations/{sim["id"]}/messages', json={'text': text, 'mode': 'script', **extra}))
    # A supported pricing request: it asks, then saves on the answer.
    q = next(e for e in say('Price Phosfusion 65-35 against TSP') if e['type'] == 'question')['payload']
    done = say('Use 655.18', answer={'option': 'standard', 'question': q['text'], 'resume': q['resume'], 'summary': q['summary']})
    assert [e['type'] for e in done][:3] == ['tool', 'text', 'result'] and done[-1]['payload'] == {'mode': 'script'}
    # An unsupported request: it says so and runs nothing.
    unknown = say('Write me a poem about fertilizer')
    assert [e['type'] for e in unknown] == ['text', 'suggest', 'done'] and unknown[0]['payload']['code'] == 'unsupported_request'
    # A data-freshness request.
    check = say('Check my data for gaps')
    assert check[0]['payload']['content'].startswith('I checked the data you have uploaded. One point needs attention:') and check[1]['payload']['code'] == 'D1'
    # A failure: the stream ends with the reason, not a broken connection.
    failed = say('Run', input={'productIds': ['phos-65-35'], 'costPlusMargin': 50})
    assert [e['type'] for e in failed] == ['error', 'done'] and failed[0]['payload']['message'] == 'costPlusMargin: must be between 0 and 2 (fraction)'
    assert len(client.get(f'/api/simulations/{sim["id"]}').json()['runs']) == 1


@pytest.mark.parametrize('name, arguments, refused', [
    ('run_engine', '{"product_ids": ["phos-65-35"], "reference_id": "TSP"}', None),
    ('run_pricing', '{}', None),
    ('drop_tables', '{}', "'drop_tables' is not a tool of this agent"),
    ('run_engine', '{"product_ids": "phos-65-35"}', 'product_ids must be a array'),
    ('run_engine', '{"sql": "delete"}', 'unknown argument(s): sql'),
    ('run_engine', '{not json', 'the arguments are not valid JSON'),
    ('run_engine', '[1]', 'the arguments must be a JSON object'),
])
def test_a_model_s_tool_call_is_checked_before_it_runs(name, arguments, refused):
    assert validate_tool_call(name, arguments)[1] == refused
