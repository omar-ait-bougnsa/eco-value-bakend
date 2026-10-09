"""Unit tests for agent tools."""
import pytest
from app.agent.tools import (
    tool_ask_user,
    tool_check_inputs,
    tool_compare_runs,
    tool_draft_memo,
    tool_explain_flags,
    tool_explain_run,
    tool_read_inputs,
    tool_run_engine,
    tool_run_pricing,
    tool_run_sulphur_sensitivity,
    tool_snapshot_view,
    tool_stage_change,
)


def test_tool_read_inputs(store):
    sim = store.add_sim('Test Read Inputs')
    data, facts, events = tool_read_inputs(store, sim.id)

    assert 'Today' in data['activeSnapshot'] or 'Year' in data['activeSnapshot']
    assert 'sulphur' in data['inputs']

    fact_keys = {f.key for f in facts}
    assert 'input_price_sulphur' in fact_keys
    assert 'ref_price_TSP' in fact_keys

    event_types = [e.type for e in events]
    assert 'step' in event_types
    assert 'tool' in event_types


def test_tool_run_engine(store):
    sim = store.add_sim('Test Sim')
    data, facts, events = tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    assert data['version'] == 1
    assert data['anchorPrice'] == pytest.approx(313.91, abs=0.01)

    fact_map = {f.key: f.value for f in facts}
    assert fact_map['unit_cost'] == pytest.approx(310.90, abs=0.01)
    assert fact_map['cgm'] == pytest.approx(3.02, abs=0.01)
    assert fact_map['cgm_ref'] == pytest.approx(-15.18, abs=0.01)

    event_types = [e.type for e in events]
    assert 'step' in event_types
    assert 'tool' in event_types
    assert 'result' in event_types

    # Ensure tool_run_pricing backward compatibility alias works identically
    assert tool_run_pricing == tool_run_engine


def test_tool_check_inputs(store):
    sim = store.add_sim('Test Flags')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    data, facts, events = tool_check_inputs(store, sim.id)
    assert 'P1' in data['flags']
    assert any(e.type == 'flag' for e in events)


def test_tool_compare_runs(store):
    sim = store.add_sim('Test Compare')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')
    # Create run 2 with 50% value share
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP', overrides={'valueShare': 0.5})

    data, facts, events = tool_compare_runs(store, sim.id)
    assert data['versionA'] == 1
    assert data['versionB'] == 2
    assert len(data['inputDiffs']) >= 1
    assert any(e.type == 'tool' for e in events)


def test_tool_snapshot_view(store):
    sim = store.add_sim('Test Snapshot View')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    data, facts, events = tool_snapshot_view(store, sim.id, '2024', ['phos-65-35'])
    assert data['snapshot'] == '2024'
    assert 'anchorPrice' in data
    assert any(e.type == 'tool' for e in events)


def test_tool_draft_memo(store):
    sim = store.add_sim('Test Memo')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    data, facts, events = tool_draft_memo(store, sim.id)
    assert len(data['blocks']) >= 3
    assert any(e.type == 'tool' for e in events)


def test_tool_explain_flags_and_run(store):
    sim = store.add_sim('Test Explanations')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    flags_data, _, f_events = tool_explain_flags(store, sim.id)
    assert len(flags_data['explanations']) >= 1

    run_data, _, r_events = tool_explain_run(store, sim.id)
    assert 'Reference-Minus' in run_data['explanation']


def test_tool_run_sulphur_sensitivity(store):
    data, facts, events = tool_run_sulphur_sensitivity(store, 'phos-65-35', 'TSP', 100, 1000, 50)
    assert data['pointCount'] == 19

    fact_map = {f.key: f.value for f in facts}
    assert fact_map['break_even_phos-65-35_zero_margin'] == pytest.approx(918.86, abs=0.01)
    assert fact_map['break_even_TSP_zero_margin'] == pytest.approx(870.41, abs=0.01)
    assert fact_map['break_even_phos-65-35_crossover'] == pytest.approx(848.46, abs=0.01)


def test_tool_stage_change(store):
    sim = store.add_sim('Test What-If')
    tool_run_engine(store, sim.id, ['phos-65-35'], 'TSP')

    change, events = tool_stage_change(
        store=store,
        simulation_id=sim.id,
        patch={'valueShare': 0.5},
        label='Value share 50%',
        reason='Test 50% capture',
    )

    assert change.status == 'staged'
    assert change.patch == {'valueShare': 0.5}
    assert change.before['valueShare'] == pytest.approx(1.0 / 3.0, abs=0.01)
    assert change.after['valueShare'] == 0.5
    assert events[0].type == 'change'


def test_tool_ask_user():
    data, events = tool_ask_user(
        question='Choose Netback or FOB?',
        options=[
            {'id': 'netback', 'label': 'Use Netback (642 USD/t)'},
            {'id': 'fob', 'label': 'Use FOB Morocco (699 USD/t)'},
        ],
    )
    assert len(data['options']) == 2
    assert events[0].type == 'question'
