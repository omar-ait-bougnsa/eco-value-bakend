from datetime import date

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def test_swagger_is_served():
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').json()['info']['title'] == 'Eco Value Simulator API'


def test_seed_data():
    assert len(client.get('/api/products').json()) == 12
    assert len(client.get('/api/products', params={'family': 'reference'}).json()) == 3
    assert len(client.get('/api/snapshots').json()) == 6
    assert len(client.get('/api/uploads').json()) == 5
    assert [s['id'] for s in client.get('/api/simulations').json()] == ['s2', 's3']


def test_engine_run_defaults_and_overrides():
    r = client.post('/api/engine/run', json={}).json()
    lead = r['output']['perProduct']['phos-65-35']
    assert round(lead['anchorPrice'], 2) == 313.91
    assert lead['waterfall'][0].keys() >= {'from', 'to'}
    r = client.post('/api/engine/run', json={'valueShare': 0.5}).json()
    assert round(r['output']['perProduct']['phos-65-35']['prices']['value'], 2) == 791.48


def test_engine_run_rejects_bad_input():
    assert client.post('/api/engine/run', json={'valueShare': 2}).status_code == 400
    assert client.post('/api/engine/run', json={'productIds': ['nope']}).status_code == 400
    assert client.post('/api/engine/run', json={'valueShre': 0.5}).status_code == 400
    assert client.post('/api/engine/run', content='{"cropPrice": NaN}', headers={'content-type': 'application/json'}).status_code == 400
    assert client.post('/api/engine/run', json={'cropPrice': 1e308, 'yieldGain': 1e10}).status_code == 400


def test_simulation_lifecycle():
    sim = client.post('/api/simulations', json={'title': 'Phosfusion 65-35 vs TSP'}).json()
    runs = f'/api/simulations/{sim["id"]}/runs'
    v1 = client.post(runs, json={'input': {'resolved': {'S1': 'standard'}}}).json()
    assert v1['version'] == 1 and v1['changed'] == [] and v1['summary'] == 'Initial run'

    v2 = client.post(runs, json={'input': {'valueShare': 0.5}, 'createdBy': 'agent', 'summary': 'Value share 33.3% → 50%'}).json()
    assert v2['version'] == 2 and v2['changed'] == ['valueShare'] and v2['editedKeys'] == ['valueShare']
    assert v2['input']['resolved'] == {'S1': 'standard'}  # carried over from v1
    assert round(v2['output']['perProduct']['phos-65-35']['prices']['value'], 2) == 791.48

    v3 = client.post(runs, json={'input': {'resolved': {'C2': True}}}).json()
    assert v3['input']['resolved'] == {'S1': 'standard', 'C2': True}  # one flag resolved, earlier answers kept

    v4 = client.post(runs, json={'input': {**v3['input'], 'resolved': {}}, 'replace': True}).json()
    assert v4['input']['resolved'] == {} and v4['input']['valueShare'] == 0.5

    assert client.get(f'{runs}/1').json()['id'] == v1['id']
    assert client.get(f'{runs}/5').status_code == 404

    copy = client.post(f'/api/simulations/{sim["id"]}/duplicate').json()
    assert copy['title'].endswith('(copy)') and len(copy['runs']) == 4
    assert client.patch(f'/api/simulations/{copy["id"]}', json={'title': 'Renamed'}).json()['title'] == 'Renamed'
    assert client.delete(f'/api/simulations/{copy["id"]}').status_code == 204
    assert client.get(f'/api/simulations/{copy["id"]}').status_code == 404
    assert client.get('/api/simulations').json()[0]['id'] == sim['id']


def test_products():
    cost = client.get('/api/products/phos-65-35/cost').json()
    assert round(cost['rawMaterial'], 2) == 310.9
    body = {'name': 'Phosfusion 70-30', 'recipe': {'rockDry': 0.7, 'sulphur': 0.1}, 'composition': {'P2O5': 0.24}}
    created = client.post('/api/products', json=body)
    assert created.status_code == 201 and created.json()['id'] == 'phosfusion-70-30'
    assert client.post('/api/products', json=body).status_code == 400  # a name is used once
    assert client.post('/api/products', json={'name': 'Neg', 'recipe': {'sulphur': -1}}).status_code == 400
    body['recipe']['sulphur'] = 0.2
    assert client.put('/api/products/phosfusion-70-30', json=body).json()['recipe']['sulphur'] == 0.2
    assert client.post('/api/products/recipe-cost', json={'recipe': body['recipe']}).json()['rawMaterial'] == pytest.approx(0.7 * 120 + 0.2 * 900)
    assert client.get('/api/products/nope').status_code == 404
    assert client.get('/api/products/TSP/cost', params={'periodTo': '2024-06-30'}).status_code == 400
    assert client.post('/api/products', json={'name': 'فوسفات', 'recipe': {'rockDry': 1}}).status_code == 201


def test_first_run_takes_agronomy_from_the_product():
    tsp = client.get('/api/products/phos-65-35').json()
    tsp.pop('id')
    client.put('/api/products/phos-65-35', json={**tsp, 'pcf': 0.3, 'yieldGain': 0.3})
    input = client.post('/api/engine/run', json={}).json()['input']
    assert input['pcfNew'] == 0.3 and input['yieldGain'] == 0.3 and input['appRateNew'] == 0.162
    cr = client.post('/api/engine/run', json={'productIds': ['phos-65-35-cr'], 'referenceId': 'DAP'}).json()['input']
    assert cr['yieldGain'] == 0.12 and cr['pcfRef'] == 0.7 and cr['appRateRef'] == 0.13  # workbook figures where a product has none


def test_a_broken_product_does_not_break_other_endpoints():
    assert client.put('/api/products/phos-65-35', json={'name': 'x', 'recipe': {'rockDry': 1e308}}).status_code == 400
    assert client.post('/api/engine/run', json={'periodFrom': '2025-12-31', 'periodTo': '2025-01-01'}).status_code == 400
    assert client.patch('/api/parameters', json={'freshnessMonths': 0}).status_code == 400
    assert client.patch('/api/parameters', json={'costPlusMargin': 1e308}).status_code == 400
    assert client.get('/api/uploads/freshness').status_code == 200


def test_parameters_feed_new_runs():
    assert client.patch('/api/parameters', json={'costPlusMargin': 0.3}).json()['costPlusMargin'] == 0.3
    assert client.get('/api/parameters/default-run-input').json()['costPlusMargin'] == 0.3
    assert client.patch('/api/parameters', json={'valueShare': 5}).status_code == 400
    assert client.get('/api/parameters/defaults').json()['costPlusMargin'] == 0.2
    assert client.post('/api/parameters/reset').json()['costPlusMargin'] == 0.2


SAMPLES = pathlib.Path(__file__).parent.parent / 'sample-uploads'


def sample(name: str):
    return {'file': (name, (SAMPLES / name).read_bytes())}


def test_newer_prices_resolve_the_freshness_flag():
    assert client.get('/api/uploads/freshness').json()['d1']['title'] == 'Prices are 5 months older than freight'
    found = client.post('/api/uploads/detect', files=sample('argus-fob-morocco-30-09-2026.xlsx')).json()
    assert found['type'] == 'prices' and found['dataThrough'] == '2026-09-30' and found['resolves'] and found['problems'] == []
    assert len(client.get('/api/uploads').json()) == 5  # detect does not save

    saved = client.post('/api/uploads', files=sample('argus-fob-morocco-30-09-2026.xlsx'))
    assert saved.status_code == 201
    assert saved.json()['name'] == 'argus-fob-morocco-30-09-2026.xlsx' and saved.json()['uploadedAt'] == date.today().isoformat()
    fresh = client.get('/api/uploads/freshness').json()
    assert fresh['d1'] is None and fresh['latest']['id'] == saved.json()['id']
    assert client.post('/api/uploads/detect', files={'file': ('photo.png', b'x')}).json()['problems'] == ['only .xlsx, .csv, .pdf, .docx, .txt, .md files are accepted']


def test_resolve_snapshot_and_presets():
    r = client.get('/api/snapshots/resolve', params={'periodFrom': '2024-07-01', 'periodTo': '2025-06-30'}).json()
    assert set(r['weights']) == {'2024', '2025'} and r['snapshot']['id'] == 'period'
    assert client.get('/api/snapshots/2025').json()['inputs']['sulphur'] == 299.2
    assert [p['id'] for p in client.get('/api/periods/presets').json()][:3] == ['ytd', 'l12', '2025']


def test_engine_sensitivity_endpoint():
    r = client.post('/api/engine/sensitivity', json={}).json()
    assert len(r['points']) == 19
    bes = {(b['productId'], b['kind']): b['sulphurPrice'] for b in r['breakEvens']}
    assert bes[('phos-65-35', 'zero_margin')] == pytest.approx(918.86, abs=0.01)
    assert bes[('TSP', 'zero_margin')] == pytest.approx(870.41, abs=0.01)
    assert bes[('phos-65-35', 'crossover')] == pytest.approx(848.46, abs=0.01)



def test_data_range_is_served():
    assert client.get('/api/periods/range').json() == {'from': '2021-01-01', 'to': '2026-10-02'}


def test_run_compares_with_the_reference():
    out = client.post('/api/engine/run', json={}).json()['output']
    r = out['perProduct']['phos-65-35']
    assert r['deltaVsRef'] == pytest.approx(r['cgm'] - r['cgmRef'])
    assert r['costVsRef'] == pytest.approx(r['unitCost'] - r['refCost'])
    assert r['cgmRefP2O5'] == pytest.approx(r['cgmRef'] / 0.46)
    sulphur = next(l['usd'] for l in r['lines'] if l['id'] == 'sulphur')
    assert r['sulphurShare'] == pytest.approx(sulphur / r['unitCost'])


def test_s1_flag_carries_its_answers():
    flags = client.post('/api/engine/run', json={}).json()['output']['flags']
    s1 = next(f for f in flags if f['code'] == 'S1')
    assert [(o['id'], o['refCostOverride']) for o in s1['options']] == [('standard', None), ('deck', 494)]
    assert s1['options'][0]['label'] == 'Use 655.18'


def test_freshness_names_the_price_files_behind_freight():
    f = client.get('/api/uploads/freshness').json()
    assert f['d1'] is not None
    assert f['behind'] == {'u1': 5}


def test_marketing_is_a_cost_in_the_margin():
    # Correction X2 (engine.md): at 10% marketing the unit cost is 341.99 and the anchor 313.91 earns −28.07, not +3.02.
    r = client.post('/api/engine/run', json={'marketingPct': 0.1}).json()['output']['perProduct']['phos-65-35']
    assert r['unitCost'] == pytest.approx(341.99, abs=0.01) and r['cgm'] == pytest.approx(-28.07, abs=0.01)
    assert all(m['cgm'] == pytest.approx(m['price'] - r['unitCost']) for m in r['methods'] if m['price'] is not None)
    # The bridge from the reference's margin ends on the product's.
    steps = r['waterfall']
    assert steps[2]['to'] == pytest.approx(r['cgm']) and steps[3]['to'] == pytest.approx(r['cgm'])


def test_quote_flags_say_what_the_price_data_says():
    flags = lambda body: {f['code']: f for f in client.post('/api/engine/run', json=body).json()['output']['flags']}
    assert not {'Q1', 'Q2'} & set(flags({}))
    assert flags({'priceType': 'high'})['Q2']['title'] == 'No high TSP quote for Today — the low quote (640) is used'
    assert not {'Q1', 'Q2'} & set(flags({'priceType': 'high', 'referenceId': 'DAP'}))  # DAP has both quotes, in order


def test_sulphur_crossover_is_where_the_margins_meet_with_marketing():
    client.patch('/api/parameters', json={'marketingPct': 0.1})
    r = client.post('/api/engine/sensitivity', json={}).json()
    cross = next(b['sulphurPrice'] for b in r['breakEvens'] if b['kind'] == 'crossover')
    a, b = r['points'][0], r['points'][-1]  # the margin gap is a straight line: where it crosses zero
    zero = a['sulphurPrice'] - a['deltaCgm'] * (b['sulphurPrice'] - a['sulphurPrice']) / (b['deltaCgm'] - a['deltaCgm'])
    assert cross == pytest.approx(zero, abs=0.01)


def test_detect_reads_the_file():
    quotes = b'Product,Date,Low USD/t,High USD/t\nDAP,2026-09-28,815,850\nTSP,2026-09-30,710,691\n'
    found = client.post('/api/uploads/detect', files={'file': ('quotes.csv', quotes)}).json()
    assert found['type'] == 'prices' and found['dataThrough'] == '2026-09-30' and found['series'] == '2 rows'
    assert found['warn'].startswith('TSP quote: low 710 > high 691.')
    clean = client.post('/api/uploads/detect', files={'file': ('quotes.csv', quotes.replace(b'710,691', b'645,668'))}).json()
    assert clean['warn'] is None
    assert client.post('/api/uploads/detect', files={'file': ('routes.csv', b'Route,Week ending,USD/t\nJorf-Santos,2026-10-01,25.5\n')}).json()['type'] == 'freight'
    unread = client.post('/api/uploads/detect', files={'file': ('argus-fob-morocco-30-09-2026.xlsx', b'not a workbook')}).json()
    assert unread['series'] == 'Not read' and unread['problems'][0].startswith('could not be read as a .xlsx file') and not unread['resolves']


def test_presets_follow_the_data_range():
    last = client.get('/api/periods/presets').json()[-1]
    assert last == {'id': '2021-25', 'label': '2021–2025', 'period': {'from': '2021-01-01', 'to': '2025-12-31'}}
