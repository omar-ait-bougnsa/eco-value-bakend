"""Tests for the agent loop and mock OpenRouter interactions."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agent.loop import run_agent_turn
from app.agent.router import get_budget_status, route_turn


def _run(coro):
    return asyncio.run(coro)


async def _collect(gen):
    return [e async for e in gen]


def test_router_status():
    budget = get_budget_status()
    assert budget['cap_usd'] == 40.0
    assert budget['spent_usd'] >= 0.0

    # Without key, routes to script
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': '', 'openrouter_api_key': ''}):
        assert route_turn() == 'script'

    # With lowercase openrouter_api_key, routes to llm
    with patch.dict('os.environ', {'openrouter_api_key': 'test_lower_key', 'OPENROUTER_API_KEY': ''}):
        assert route_turn() == 'llm'


def test_agent_turn_mock_openrouter_execution(store):
    sim = store.add_sim('Mock LLM Test')

    # Step 1: Model calls run_pricing
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        'choices': [{
            'message': {
                'role': 'assistant',
                'tool_calls': [{
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'run_pricing',
                        'arguments': '{"product_ids": ["phos-65-35"], "reference_id": "TSP"}',
                    },
                }],
            }
        }]
    }

    # Step 2: Model emits verified text quoting the facts
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': 'Recommended anchor is 313.91 USD/t with a CGM of 3.02 USD/t.',
            }
        }]
    }

    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'mock_key'}):
        with patch('httpx.AsyncClient.post', side_effect=[mock_resp_1, mock_resp_2]):
            events = _run(_collect(run_agent_turn(store, sim.id, 'Price Phosfusion against TSP')))

    event_types = [e.type for e in events]
    assert 'step' in event_types
    assert 'tool' in event_types
    assert 'text' in event_types
    # The model priced a preview: nothing is saved until the user confirms.
    assert 'result' not in event_types and not sim.runs
    q = next(e for e in events if e.type == 'question').payload
    assert [o['id'] for o in q['options']] == ['save', 'discard'] and q['resume']['productIds'] == ['phos-65-35']


def test_agent_turn_mock_openrouter_run_engine(store):
    sim = store.add_sim('Mock LLM Run Engine Test')

    # Step 1: Model calls run_engine
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        'choices': [{
            'message': {
                'role': 'assistant',
                'tool_calls': [{
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'run_engine',
                        'arguments': '{"product_ids": ["phos-65-35"], "reference_id": "TSP"}',
                    },
                }],
            }
        }]
    }

    # Step 2: Model emits verified text
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': 'Valuation completed: Anchor 313.91 USD/t.',
            }
        }]
    }

    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'mock_key'}):
        with patch('httpx.AsyncClient.post', side_effect=[mock_resp_1, mock_resp_2]):
            events = _run(_collect(run_agent_turn(store, sim.id, 'Price Phosfusion with run_engine')))

    event_types = [e.type for e in events]
    assert 'tool' in event_types
    assert 'question' in event_types and not sim.runs
    assert any(e.type == 'tool' and e.payload['name'] == 'run_engine' for e in events)
    assert 'done' in event_types

    # The user's click saves it, through the built-in agent: the model does not write.
    from app.agent.fallback import run_scripted_turn
    q = next(e for e in events if e.type == 'question').payload
    saved = _run(_collect(run_scripted_turn(store, sim.id, 'Save', answer={'option': 'save', 'resume': q['resume'], 'summary': q['summary']})))
    assert 'result' in [e.type for e in saved] and [r.version for r in sim.runs] == [1]
    kept = _run(_collect(run_scripted_turn(store, sim.id, 'No', answer={'option': 'discard', 'resume': q['resume']})))
    assert [e.type for e in kept] == ['text', 'done'] and len(sim.runs) == 1

    text_e = next(e for e in events if e.type == 'text')
    assert '313.91 USD/t' in text_e.payload['content']

