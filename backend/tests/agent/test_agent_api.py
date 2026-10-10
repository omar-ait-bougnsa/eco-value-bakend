"""Tests for agent API endpoints and SSE streaming."""
import json
import pytest
from fastapi.testclient import TestClient

from app.agent.service import register_staged_change
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def test_agent_status_endpoint():
    r = client.get('/api/agent/status').json()
    assert 'mode' in r
    assert r['budget']['cap_usd'] == 40.0


def frames_of(resp):
    return [json.loads(line[5:]) for line in resp.text.splitlines() if line.startswith('data:')]


def events_of(resp):
    """The turn's events, without the two `job` frames around them."""
    return [e for e in frames_of(resp) if e['type'] != 'job']


def test_post_simulation_message_sse_streaming():
    sim = client.post('/api/simulations', json={'title': 'Agent Chat Test'}).json()
    url = f'/api/simulations/{sim["id"]}/messages'
    resp = client.post(url, json={'text': 'Price Phosfusion 65-35 against TSP', 'mode': 'script'})
    assert resp.status_code == 200
    assert 'text/event-stream' in resp.headers['content-type']
    assert [e['type'] for e in events_of(resp)] == ['step', 'flag', 'question', 'done']

    # The answer goes back with what the question gave, and the run is saved.
    q = next(e for e in events_of(resp) if e['type'] == 'question')['payload']
    answered = events_of(client.post(url, json={'text': 'Use 494', 'answer': {'option': 'deck', 'question': q['text'], 'resume': q['resume'], 'summary': q['summary']}}))
    assert [e['type'] for e in answered][:3] == ['tool', 'text', 'result']
    saved = client.get(f'/api/simulations/{sim["id"]}').json()
    assert saved['title'] == 'Phosfusion 65-35 vs TSP' and saved['runs'][0]['input']['refCostOverride'] == 494


def test_a_run_input_is_priced_by_the_built_in_agent_whatever_the_mode():
    sim = client.post('/api/simulations', json={'title': 'Form'}).json()
    events = events_of(client.post(f'/api/simulations/{sim["id"]}/messages', json={'text': 'Run', 'mode': 'llm', 'input': {'productIds': ['phos-50-50'], 'referenceId': 'DAP'}}))
    assert events[-1] == {**events[-1], 'type': 'done', 'payload': {'mode': 'script'}}
    assert client.get(f'/api/simulations/{sim["id"]}').json()['runs'][0]['input']['referenceId'] == 'DAP'


def test_bad_input_is_an_error_event_not_a_broken_stream():
    sim = client.post('/api/simulations', json={'title': 'Form'}).json()
    events = events_of(client.post(f'/api/simulations/{sim["id"]}/messages', json={'text': 'Run', 'input': {'productIds': ['nope']}}))
    assert [e['type'] for e in events] == ['error', 'done'] and 'nope' in events[0]['payload']['message']


def test_agent_prompts_endpoint():
    r = client.get('/api/agent/prompts').json()
    assert r['start'][0] == 'Price Phosfusion 65-35 against TSP' and 'Show the sulphur break-even' in r['next']


def test_apply_and_dismiss_staged_change():
    sim = client.post('/api/simulations', json={'title': 'Change Apply Test'}).json()
    # Initial run v1
    v1 = client.post(f'/api/simulations/{sim["id"]}/runs', json={}).json()
    assert v1['version'] == 1

    # Register a staged change
    change_id = 'c_test_123'
    register_staged_change(change_id, {
        'id': change_id,
        'simulationId': sim['id'],
        'baseVersion': 1,
        'label': 'Value share 50%',
        'patch': {'valueShare': 0.5},
        'status': 'staged',
    })

    # Apply staged change
    res = client.post(f'/api/changes/{change_id}/apply', json={'summary': 'Applied 50% value share'})
    assert res.status_code == 201
    v2 = res.json()
    assert v2['version'] == 2
    assert v2['input']['valueShare'] == 0.5

    # Dismiss another change
    change_id_2 = 'c_test_456'
    register_staged_change(change_id_2, {
        'id': change_id_2,
        'simulationId': sim['id'],
        'baseVersion': 2,
        'label': 'Marketing 10%',
        'patch': {'marketingPct': 0.1},
        'status': 'staged',
    })
    dis = client.post(f'/api/changes/{change_id_2}/dismiss')
    assert dis.status_code == 204

