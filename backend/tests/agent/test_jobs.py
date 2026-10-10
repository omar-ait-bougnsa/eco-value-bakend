"""Agent jobs: the state of every turn is stored, ends, and says why when it fails."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import jobs, router
from app.agent.types import AgentEvent
from app.db import JobRow
from app.main import app

client = TestClient(app)
RUN = {'productIds': ['phos-50-50'], 'referenceId': 'DAP'}


@pytest.fixture(autouse=True)
def fresh():
    client.post('/api/reset')


def new_sim() -> str:
    return client.post('/api/simulations', json={'title': 'Jobs'}).json()['id']


def send(sim: str, text: str = 'Run', **body):
    r = client.post(f'/api/simulations/{sim}/messages', json={'text': text, 'mode': 'script', **body})
    frames = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith('data:')]
    return r, frames, client.get(f'/api/jobs/{r.headers["x-job-id"]}').json()


def test_a_successful_run_reaches_completed_and_is_what_a_reload_reads():
    sim = new_sim()
    r, frames, job = send(sim, input=RUN)
    assert frames[0]['type'] == 'job' and frames[0]['payload']['state'] == 'running'
    assert frames[-1]['type'] == 'job' and (frames[-1]['payload']['id'], frames[-1]['payload']['state']) == (job['id'], 'completed')
    assert (job['state'], job['kind'], job['mode'], job['result']) == ('completed', 'run', 'script', {'outcome': 'run', 'runVersion': 1})
    assert [t['state'] for t in job['transitions']] == ['queued', 'running', 'completed'] and all(t['at'] for t in job['transitions'])
    assert job['startedAt'] and job['finishedAt'] and job['error'] is None and job['id'] == r.headers['x-job-id']
    saved = client.get(f'/api/simulations/{sim}').json()
    assert saved['job'] == job and [run['version'] for run in saved['runs']] == [1]
    assert [j['id'] for j in client.get(f'/api/simulations/{sim}/jobs').json()] == [job['id']]


def test_a_refused_input_reaches_failed_with_the_reason():
    sim = new_sim()
    _, frames, job = send(sim, input={**RUN, 'costPlusMargin': 50})
    assert (job['state'], job['failureCode'], job['error']) == ('failed', 'invalid_input', 'costPlusMargin: must be between 0 and 2 (fraction)')
    assert [t['state'] for t in job['transitions']] == ['queued', 'running', 'failed']
    error = next(f for f in frames if f['type'] == 'error')['payload']
    assert error == {'message': job['error'], 'code': 'invalid_input', 'fatal': True}
    assert client.get(f'/api/simulations/{sim}').json()['runs'] == []


def test_a_crash_is_logged_with_the_job_id_and_shown_without_its_cause(caplog):
    async def broken(*a, **k):
        raise RuntimeError('database exploded at 10.0.0.5')
        yield  # pragma: no cover
    with patch.object(jobs, 'agent_events', broken), caplog.at_level(logging.ERROR, logger='evs.jobs'):
        _, _, job = send(new_sim())
    assert (job['state'], job['failureCode']) == ('failed', 'internal_error')
    assert job['id'] in job['error'] and 'exploded' not in job['error']
    assert f'job={job["id"]}' in caplog.text and 'database exploded at 10.0.0.5' in caplog.text  # the cause is in the log, under the same id


def test_a_job_that_takes_too_long_is_timed_out_and_can_be_retried():
    async def stuck(*a, **k):
        yield AgentEvent(id='s1', type='step', payload={'label': 'Waiting for something that never answers', 'status': 'running'})
        await asyncio.sleep(30)
    sim = new_sim()
    with patch.object(jobs, 'agent_events', stuck), patch.object(jobs, 'TIMEOUT_SECONDS', 0.05):
        _, frames, job = send(sim, input=RUN)
    assert (job['state'], job['failureCode']) == ('timed_out', 'timed_out') and job['finishedAt']
    assert [f['type'] for f in frames] == ['job', 'step', 'error', 'job'] and frames[2]['payload']['code'] == 'timed_out'
    # Retry: the same request, as the job kept it.
    _, _, again = send(sim, job['request']['text'], input=job['request']['input'])
    assert again['state'] == 'completed' and again['id'] != job['id'] and again['result']['runVersion'] == 1


def test_a_job_outlives_the_request_and_a_reload_sees_its_real_state():
    """The browser goes away while the job runs: the job goes on, and whoever asks next is told where it is."""
    async def scenario():
        gate = asyncio.Event()

        async def slow(*a, **k):
            yield AgentEvent(id='s1', type='step', payload={'label': 'Working', 'status': 'running'})
            await gate.wait()
            yield AgentEvent(id='d1', type='done', payload={'mode': 'script'})

        with patch.object(jobs, 'agent_events', slow):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
                sim = (await c.post('/api/simulations', json={'title': 'Reload'})).json()['id']
                stream = asyncio.create_task(c.post(f'/api/simulations/{sim}/messages', json={'text': 'Run', 'mode': 'script'}))
                for _ in range(100):
                    seen = (await c.get(f'/api/simulations/{sim}')).json()['job']
                    if seen and seen['state'] == 'running':
                        break
                    await asyncio.sleep(0.01)
                assert seen['state'] == 'running' and seen['finishedAt'] is None
                stream.cancel()  # the page is reloaded: the request that started the job is gone
                await asyncio.gather(stream, return_exceptions=True)
                assert (await c.get(f'/api/jobs/{seen["id"]}')).json()['state'] == 'running'
                gate.set()
                for _ in range(100):
                    after = (await c.get(f'/api/jobs/{seen["id"]}')).json()
                    if after['state'] != 'running':
                        break
                    await asyncio.sleep(0.01)
                return after
    assert asyncio.run(scenario())['state'] == 'completed'


def test_a_running_job_can_be_cancelled():
    async def scenario():
        async def slow(*a, **k):
            yield AgentEvent(id='s1', type='step', payload={'label': 'Working', 'status': 'running'})
            await asyncio.sleep(30)
        with patch.object(jobs, 'agent_events', slow):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
                sim = (await c.post('/api/simulations', json={'title': 'Cancel'})).json()['id']
                stream = asyncio.create_task(c.post(f'/api/simulations/{sim}/messages', json={'text': 'Run', 'mode': 'script'}))
                for _ in range(100):
                    seen = (await c.get(f'/api/simulations/{sim}')).json()['job']
                    if seen and seen['state'] == 'running':
                        break
                    await asyncio.sleep(0.01)
                await c.post(f'/api/jobs/{seen["id"]}/cancel')
                await stream
                return (await c.get(f'/api/jobs/{seen["id"]}')).json()
    job = asyncio.run(scenario())
    assert (job['state'], job['failureCode']) == ('cancelled', 'cancelled')
    assert client.post(f'/api/jobs/{job["id"]}/cancel').json()['state'] == 'cancelled'  # ended: left as it is


def test_no_job_stays_running_forever(store):
    """A job the server lost (it restarted) has nobody to end it: it is ended the first time someone looks."""
    sim = store.add_sim('Lost')
    old = datetime.now(timezone.utc) - timedelta(seconds=jobs.TIMEOUT_SECONDS + 60)
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    for id, at in (('jlost', old), ('jrecent', recent)):
        store.db.add(JobRow(id=id, simulationId=sim.id, kind='message', state='running', request={'text': 'Price it'}, transitions=[{'state': 'running', 'at': at.isoformat()}], createdAt=at, startedAt=at))
    store.db.commit()
    lost = client.get('/api/jobs/jlost').json()
    assert (lost['state'], lost['failureCode']) == ('timed_out', 'lost') and 'try it again' in lost['error'] and lost['finishedAt']
    assert client.get('/api/jobs/jrecent').json()['state'] == 'running'  # still inside its time
    assert {j['id']: j['state'] for j in client.get(f'/api/simulations/{sim.id}/jobs').json()} == {'jlost': 'timed_out', 'jrecent': 'running'}
    assert client.get('/api/jobs/nope').status_code == 404


def test_rule_based_assistant_supported_and_unsupported_requests():
    sim = new_sim()
    _, frames, job = send(sim, 'give me information about product TSP')
    card = next(f for f in frames if f['type'] == 'text')['payload']['content']
    assert card.startswith('**TSP** (reference)') and '- Composition: P2O5 46%' in card and '- Raw-material cost: 655.18 USD/t · Today prices, as of 02 Oct 2026' in card
    assert job['state'] == 'completed' and job['result']['outcome'] == 'answer'

    _, frames, job = send(sim, 'Write me a poem about fertilizer')
    refusal = next(f for f in frames if f['type'] == 'text')['payload']
    assert refusal['code'] == 'unsupported_request' and [s['label'] for s in refusal['suggestions']][:2] == ['Price a product', 'Product information']
    assert job['state'] == 'completed' and job['result'] == {'outcome': 'unsupported', 'runVersion': None}
    prompts = client.get('/api/agent/prompts').json()
    assert prompts['supported'] == refusal['suggestions']


def _reply(message: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {'choices': [{'message': {'role': 'assistant', **message}, 'finish_reason': 'stop'}]}
    return m


def _call(name: str, arguments: dict) -> MagicMock:
    return _reply({'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]})


def ask_model(sim: str, text: str, replies: list):
    router.record_llm_success()
    router._turns.clear()
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key', 'LLM_ENABLED': 'true'}), patch('httpx.AsyncClient.post', side_effect=replies) as post:
        r = client.post(f'/api/simulations/{sim}/messages', json={'text': text})
    frames = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith('data:')]
    return frames, client.get(f'/api/jobs/{r.headers["x-job-id"]}').json(), post


def test_with_a_model_a_question_about_a_product_is_answered_from_the_library():
    sim = new_sim()
    answer = 'TSP is a reference product with 46% P2O5. Its recipe uses 0.608 t/t of dry rock and its raw-material cost is 655.18 USD/t.'
    frames, job, post = ask_model(sim, 'give me information about product TSP', [_call('get_product', {'product': 'TSP'}), _reply({'content': answer})])
    assert [f['type'] for f in frames] == ['job', 'step', 'tool', 'text', 'done', 'job']
    assert frames[2]['payload']['name'] == 'get_product' and frames[3]['payload']['content'] == answer
    assert (job['state'], job['mode'], job['result']['outcome']) == ('completed', 'llm', 'answer')
    sent = post.call_args_list[0].kwargs['json']
    assert 'get_product' in [t['function']['name'] for t in sent['tools']] and {'role': 'user', 'content': 'give me information about product TSP'} in sent['messages']
    assert client.get(f'/api/simulations/{sim}').json()['runs'] == []  # reading a product writes nothing


def test_a_model_answer_that_cannot_be_verified_is_replaced_by_what_the_tool_returned():
    invented = _reply({'content': 'TSP contains 52% P2O5.'})  # the library says 46 %
    frames, job, _ = ask_model(new_sim(), 'give me information about product TSP', [_call('get_product', {'product': 'TSP'}), invented, invented])
    text = next(f for f in frames if f['type'] == 'text')['payload']['content']
    assert text.startswith('**TSP** (reference)') and 'P2O5 46%' in text and '52' not in text and job['state'] == 'completed'


def test_a_model_outage_ends_the_job_with_the_rule_based_answer_not_a_hang():
    refused = MagicMock()
    refused.status_code = 429
    frames, job, _ = ask_model(new_sim(), 'give me information about product TSP', [refused])
    assert [f['type'] for f in frames] == ['job', 'error', 'text', 'done', 'job']
    assert frames[1]['payload']['message'].startswith('The language model did not answer') and frames[2]['payload']['content'].startswith('**TSP** (reference)')
    assert (job['state'], job['mode']) == ('completed', 'script')
    router.record_llm_success()


def test_too_many_model_turns_in_a_minute_fall_back_to_the_rule_based_assistant(monkeypatch):
    router.record_llm_success()
    router._turns.clear()
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_ENABLED', 'true')
    monkeypatch.setattr(router, 'MAX_TURNS_PER_MINUTE', 2)
    assert client.get('/api/agent/status').json()['mode'] == 'llm'
    router.record_llm_turn(); router.record_llm_turn()
    status = client.get('/api/agent/status').json()
    assert (status['mode'], status['fallbackReason'], status['label']) == ('script', 'rate_limited', 'Rule-based assistant (too many AI requests this minute)')
    router._turns.clear()
