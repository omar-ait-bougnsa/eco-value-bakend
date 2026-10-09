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


def test_post_simulation_message_sse_streaming():
    sim = client.post('/api/simulations', json={'title': 'Agent Chat Test'}).json()
    resp = client.post(
        f'/api/simulations/{sim["id"]}/messages',
        json={'text': 'Price Phosfusion 65-35 against TSP', 'mode': 'script'},
    )
    assert resp.status_code == 200
    assert 'text/event-stream' in resp.headers['content-type']

    body = resp.text
    assert 'event: step' in body
    assert 'event: question' in body
    assert 'event: result' in body
    assert 'event: text' in body
    assert 'event: done' in body


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

