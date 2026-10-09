"""Tests for the deterministic scripted fallback runner."""
import asyncio
from app.agent.fallback import run_scripted_turn


def _run(coro):
    return asyncio.run(coro)


async def _collect(gen):
    return [e async for e in gen]


def test_fallback_hero_pricing_turn(store):
    sim = store.add_sim('Hero Demo')
    events = _run(_collect(run_scripted_turn(store, sim.id, 'Price Phosfusion 65-35 against TSP')))

    event_types = [e.type for e in events]
    assert 'step' in event_types
    assert 'question' in event_types
    assert 'result' in event_types
    assert 'flag' in event_types
    assert 'text' in event_types
    assert 'done' in event_types

    # Question payload has netback option
    q_event = next(e for e in events if e.type == 'question')
    assert any('Netback' in o['label'] for o in q_event.payload['options'])

    # Text payload has golden numbers
    t_event = next(e for e in events if e.type == 'text')
    assert '313.91 USD/t' in t_event.payload['content']
    assert '3.02 USD/t' in t_event.payload['content']
    assert '-15.18 USD/t' in t_event.payload['content']


def test_fallback_what_if_turn(store):
    sim = store.add_sim('What If Demo')
    # First create initial run
    from app.agent.tools import tool_run_pricing
    tool_run_pricing(store, sim.id, ['phos-65-35'], 'TSP')

    events = _run(_collect(run_scripted_turn(store, sim.id, 'What if value share is 50%?')))
    event_types = [e.type for e in events]
    assert 'change' in event_types
    change_e = next(e for e in events if e.type == 'change')
    assert change_e.payload['patch'] == {'valueShare': 0.5}


def test_fallback_sensitivity_turn(store):
    sim = store.add_sim('Sensitivity Demo')
    events = _run(_collect(run_scripted_turn(store, sim.id, 'Show sulphur sensitivity')))

    t_event = next(e for e in events if e.type == 'text')
    assert '918.86 USD/t' in t_event.payload['content']
    assert '870.41 USD/t' in t_event.payload['content']
    assert '848.46 USD/t' in t_event.payload['content']

