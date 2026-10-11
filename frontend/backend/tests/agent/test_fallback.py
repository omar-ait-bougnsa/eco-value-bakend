"""Tests for the built-in agent: the turns it answers without a language model, from the engine and the store."""
import asyncio

import pytest

from app.agent.fallback import next_prompts, parse_products, run_scripted_turn, start_prompts


def turn(store, sim, text, **kw):
    async def collect():
        return [e async for e in run_scripted_turn(store, sim.id, text, **kw)]
    return asyncio.run(collect())


def one(events, type):
    return next(e for e in events if e.type == type)


def priced(store, option='standard'):
    """A simulation with its first run: the pricing request, then the answer to the question it asks."""
    sim = store.add_sim('Demo')
    q = one(turn(store, sim, 'Price Phosfusion 65-35 against TSP'), 'question').payload
    events = turn(store, sim, 'answer', answer={'option': option, 'question': q['text'], 'resume': q['resume'], 'summary': q['summary']})
    return sim, events


def test_pricing_asks_before_it_runs_when_the_sources_disagree(store):
    sim = store.add_sim('Demo')
    events = turn(store, sim, 'Price Phosfusion 65-35 against TSP')
    assert [e.type for e in events] == ['step', 'flag', 'question', 'done']
    assert one(events, 'flag').payload['code'] == 'D1'
    q = one(events, 'question').payload
    assert q['text'] == 'TSP full production cost differs between sources: Business-case deck 494 USD/t vs Standard cost 2026 655.18 USD/t. Which should I use?'
    assert [o['id'] for o in q['options']] == ['standard', 'deck', 'sources']
    assert q['resume']['productIds'] == ['phos-65-35'] and q['resume']['referenceId'] == 'TSP'
    assert not sim.runs  # nothing is saved before the answer


def test_the_answer_runs_v1_names_the_simulation_and_quotes_the_engine(store):
    sim, events = priced(store)
    assert [e.type for e in events] == ['tool', 'text', 'result', 'flag', 'flag', 'suggest', 'done']
    assert sim.title == 'Phosfusion 65-35 vs TSP'
    assert len(sim.runs) == 1 and sim.runs[0].input['resolved'] == {'S1': 'standard'}
    r = sim.runs[0].output['perProduct']['phos-65-35']
    assert r['anchorPrice'] == pytest.approx(313.91, abs=0.01) and r['prices']['costPlus'] == pytest.approx(373.08, abs=0.01)
    text = one(events, 'text').payload
    assert '**Recommended anchor: 313.91 USD/t (reference minus).** That is below the cost-plus floor of 373.08' in text['content']
    assert 'earns 3.02 USD/t against TSP’s −15.18 USD/t' in text['content']
    assert text['sources'] == ['Prices · 21 Apr', 'Standard cost · 2026', 'Agro trials · 12 Aug', 'Crop prices · 30 Sep']
    assert one(events, 'result').payload['version'] == 1
    assert {e.payload['code'] for e in events if e.type == 'flag'} == {'U1', 'C2'}
    assert one(events, 'suggest').payload['items'] == next_prompts(store)


def test_choosing_the_deck_cost_changes_the_reference_margin(store):
    sim, _ = priced(store, 'deck')
    assert sim.runs[0].input['refCostOverride'] == 494
    assert sim.runs[0].output['perProduct']['phos-65-35']['cgmRef'] == pytest.approx(146, abs=0.01)


def test_open_sources_searches_the_documents_and_runs_nothing(store):
    sim = store.add_sim('Demo')
    q = one(turn(store, sim, 'Price Phosfusion 65-35 against TSP'), 'question').payload
    events = turn(store, sim, 'answer', answer={'option': 'sources', 'question': q['text'], 'resume': q['resume']})
    assert 'result' not in [e.type for e in events] and not sim.runs


def test_a_given_run_input_is_priced_as_it_is(store):
    sim = store.add_sim('Demo')
    events = turn(store, sim, 'Run', input={'productIds': ['phos-50-50'], 'referenceId': 'DAP', 'costPlusMargin': 0.3})
    assert 'question' not in [e.type for e in events]  # the cost conflict is about TSP
    assert sim.runs[0].input['costPlusMargin'] == 0.3 and sim.title == 'Phosfusion 50-50 vs DAP'


def test_two_products_are_priced_in_the_order_they_are_named(store):
    assert parse_products(store, 'compare phosfusion 50-50 and phosfusion 65-35') == ['phos-50-50', 'phos-65-35']
    assert parse_products(store, 'price phosfusion against dap') == ['phos-65-35']
    assert parse_products(store, 'price the 45 55 grade') == ['phos-45-55-cr']
    sim = store.add_sim('Demo')
    events = turn(store, sim, 'Compare Phosfusion 50-50 and Phosfusion 65-35 against DAP')
    assert sim.runs[0].input['productIds'] == ['phos-50-50', 'phos-65-35']
    assert one(events, 'text').payload['content'].startswith('2 products priced against DAP:')


def test_what_if_stages_a_change_with_its_preview_and_saves_nothing(store):
    sim, _ = priced(store)
    events = turn(store, sim, 'What if the value share is 50%?')
    assert [e.type for e in events] == ['text', 'change', 'done']
    change = one(events, 'change').payload
    assert change['patch'] == {'valueShare': 0.5} and change['label'] == 'Value share kept by OCP'
    assert {'label': 'Value pricing', 'before': '740.99', 'after': '791.48'} in change['previews']
    assert len(sim.runs) == 1


@pytest.mark.parametrize('text, patch', [
    ('set the cost-plus margin to 25%', {'costPlusMargin': 0.25}),
    ('what if the carbon price is 40', {'carbonPrice': 40.0}),
    ('try a market share of 8%', {'marketShare': 0.08}),
    ('use a competitor benchmark of 350', {'benchmark': 350.0}),
    ('what if we include d&a', {'fullCost': True}),
    ('change the anchor to value pricing', {'anchor': 'value'}),
])
def test_the_inputs_a_what_if_can_change(store, text, patch):
    sim, _ = priced(store)
    assert one(turn(store, sim, text), 'change').payload['patch'] == patch


def test_another_period_is_a_view_priced_by_the_engine(store):
    sim, _ = priced(store)
    events = turn(store, sim, 'Show the 2025 analysis period')
    assert one(events, 'view').payload == {'period': {'from': '2025-01-01', 'to': '2025-12-31'}, 'tab': 'overview'}
    x = store.run(store.make_input({'periodFrom': '2025-01-01', 'periodTo': '2025-12-31'}, store.make_input(sim.runs[0].input))).perProduct['phos-65-35']
    assert f'Anchor {x.anchorPrice:,.2f} USD/t against a cost-plus floor of {x.floor:,.2f}' in one(events, 'text').payload['content']
    assert len(sim.runs) == 1


def test_explanations_and_memo_quote_the_saved_run(store):
    sim, _ = priced(store)
    assert 'That gives 313.91 USD/t. The cost-plus floor is unit cost 310.90 × (1 + 20%) = 373.08.' in one(turn(store, sim, 'Why is the anchor below the floor?'), 'text').payload['content']
    assert '= **740.99 USD/t**' in one(turn(store, sim, 'Explain the value pricing'), 'text').payload['content']
    memo = turn(store, sim, 'Draft the memo')
    assert one(memo, 'view').payload == {'memo': True}
    assert 'decision memo for v1. Analysis period: Year to date.' in one(memo, 'text').payload['content']


def test_sensitivity_is_computed_for_the_simulation_s_product(store):
    sim, _ = priced(store)
    text = one(turn(store, sim, 'Show the sulphur break-even'), 'text').payload['content']
    assert '**Phosfusion 65-35** breaks even (zero margin) at **918.86 USD/t** sulphur' in text
    assert 'Sulphur is at 900.00 USD/t today.' in text
    other = store.add_sim('Other')
    turn(store, other, 'Run', input={'productIds': ['phos-50-50'], 'referenceId': 'DAP'})
    assert '**Phosfusion 50-50** breaks even' in one(turn(store, other, 'sulphur sensitivity'), 'text').payload['content']


def test_data_check_and_latest_uploads_read_the_store(store):
    sim = store.add_sim('Demo')
    check = turn(store, sim, 'Check my data for gaps')
    assert one(check, 'text').payload['content'] == 'I checked the data you have uploaded. One point needs attention:'
    assert one(check, 'flag').payload['title'] == 'Prices are 5 months older than freight'
    latest = one(turn(store, sim, 'What changed since the last upload?'), 'text').payload['content']
    assert latest.startswith('The most recent uploads are **') and 'data through' in latest
    assert not sim.runs


def test_an_unknown_request_runs_nothing(store):
    sim, _ = priced(store)
    events = turn(store, sim, 'Why is this margin so thin compared with last quarter?')
    assert [e.type for e in events] == ['text', 'suggest', 'done']
    refusal = one(events, 'text').payload
    assert refusal['code'] == 'unsupported_request' and 'I am a rule-based assistant, not an AI model' in refusal['content']
    assert {'label': 'Product information', 'example': 'Show product TSP'} in refusal['suggestions']
    assert one(events, 'suggest').payload['items'][0] == 'Price Phosfusion 65-35 against TSP' and len(sim.runs) == 1


def test_prompts_name_the_stored_products(store):
    assert start_prompts(store)[:2] == ['Price Phosfusion 65-35 against TSP', 'Compare Phosfusion 65-35 and Phosfusion 50-50']
    assert 'Show the 2025 analysis period' in next_prompts(store)
