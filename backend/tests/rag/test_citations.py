"""The agent's `search_knowledge` tool, the provenance rules of the checker, and the `citation` events."""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import rag
from app.agent.checker import validate_agent_text
from app.agent.citations import cited, knowledge_answer
from app.agent.loop import run_agent_turn
from app.agent.tools import TOOL_DEFINITIONS, tool_search_knowledge
from app.agent.types import ToolFact
from app.main import app
from app.rag.embeddings import EmbeddingError

FREIGHTS = 'fertilizer-week-historical-freights-01-10-2026.xlsx'
QUESTION = 'freight rate from Jorf Lasfar to Santos'


@pytest.fixture
def knowledge(store):
    rag.prepare(store.db)
    return store


def retrieved(store, query=QUESTION, **kw) -> dict[str, dict]:
    return {r['ref']: r for r in tool_search_knowledge(store, query, **kw)[0]['results']}


# ───────────────────────── tool ─────────────────────────

def test_the_tool_returns_passages_with_their_source_and_a_ref(knowledge):
    data, facts, events = tool_search_knowledge(knowledge, QUESTION, limit=2)
    assert facts == [] and [e.type for e in events] == ['step', 'tool']
    assert events[1].payload['name'] == 'search_knowledge' and events[1].payload['label'] == 'Knowledge search · 2 passages'
    top = data['results'][0]
    assert {'passage', 'source', 'date', 'page', 'relevance_score'} <= set(top)  # RAG.md §5
    assert (top['ref'], top['source'], top['date'], top['page'], top['section']) == ('K1', FREIGHTS, '2026-10-01', None, 'Phosphates')
    assert top['label'] == f'{FREIGHTS}, 01-Oct-2026, Phosphates'
    assert [r['ref'] for r in data['results']] == ['K1', 'K2']
    json.dumps(data)  # it goes to the model as JSON

    # A second search in the same turn carries on the numbering, and the kind filter is passed on.
    more = tool_search_knowledge(knowledge, 'yield gain maize trials', doc_type='agronomy', limit=1, first_ref=3)[0]['results']
    assert [(r['ref'], r['source']) for r in more] == [('K3', 'agro-trials-phosfusion-2026-09-15.xlsx')]
    assert tool_search_knowledge(knowledge, 'holiday weather forecast in Paris')[0] == {'results': []}


def test_the_tool_says_when_the_search_cannot_run(knowledge):
    with patch('app.agent.tools.search', side_effect=EmbeddingError('Embedding request to openrouter.ai failed: timed out')):
        data, _, events = tool_search_knowledge(knowledge, QUESTION)
    assert data == {'results': [], 'error': 'Knowledge search is unavailable: Embedding request to openrouter.ai failed: timed out'}
    assert [e.type for e in events] == ['step']


def test_the_model_is_told_about_the_tool():
    definition = next(t['function'] for t in TOOL_DEFINITIONS if t['function']['name'] == 'search_knowledge')
    assert definition['parameters']['required'] == ['query']
    assert definition['parameters']['properties']['doc_type']['enum'] == ['market_report', 'freight', 'agronomy', 'methodology']


# ───────────────────────── citations ─────────────────────────

def test_markers_are_renumbered_in_order_of_use_with_one_event_each(knowledge):
    found = retrieved(knowledge, limit=3)
    text, events = cited('Rates rose [K2]. The Santos route is the reference [K1], as the table shows [K2]. Unknown [K9].', found)
    assert text == 'Rates rose [1]. The Santos route is the reference [2], as the table shows [1]. Unknown .'
    assert [e.type for e in events] == ['citation', 'citation']
    assert [(e.payload['index'], e.payload['chunkId']) for e in events] == [(1, found['K2']['chunkId']), (2, found['K1']['chunkId'])]
    assert events[1].payload == {
        'index': 2, 'label': f'{FREIGHTS}, 01-Oct-2026, Phosphates', 'source': FREIGHTS, 'date': '2026-10-01', 'page': None, 'section': 'Phosphates',
        'passage': found['K1']['passage'], 'relevanceScore': found['K1']['relevance_score'], 'documentId': found['K1']['documentId'], 'chunkId': found['K1']['chunkId'],
    }
    assert cited('No source used.', found) == ('No source used.', [])


def test_an_answer_made_of_the_passages_themselves(knowledge):
    results = list(retrieved(knowledge, limit=2).values())
    answer = knowledge_answer(results)
    assert answer.startswith('Here is what the indexed documents say:') and answer.count('[K') == 2
    assert f'[K1] {results[0]["passage"]}' in answer
    assert validate_agent_text(answer, {}, citations={r['ref']: r for r in results}).is_valid
    assert knowledge_answer([]) == 'I found nothing about that in the indexed documents.'
    long = knowledge_answer([{**results[0], 'passage': 'word ' * 500}])
    assert len(long) < 800 and '\n\n[K1] word word' in long and long.endswith('word …')


# ───────────────────────── checker ─────────────────────────

def check(text, citations, facts=None, grounding='', sources=()):
    return validate_agent_text(text, facts or {}, citations=citations, grounding=grounding or json.dumps({'results': list(citations.values())}, ensure_ascii=False), sources=sources)


def test_figures_dates_and_quotations_from_a_retrieved_passage_pass(knowledge):
    found = retrieved(knowledge)
    ok = check('Freight from Jorf Lasfar to Santos was 25.5 USD/t in the week ending 2026-10-01, up from 24.5 USD/t on 17 Sep 2026 [K1].', found)
    assert ok.is_valid, ok.errors
    assert check('The table lists the route as "| 2026-10-01 | Jorf Lasfar – Santos | 30 | 25.5 |" at 25.5 USD/t [K1].', found).is_valid
    # The date of the document itself is in what the tool returned, in another format.
    assert check('The file dated 01-Oct-2026 gives 25.5 USD/t [K1].', found).is_valid
    # A figure from the engine and a figure from a passage in the same answer.
    fact = {'anchor_price': ToolFact(key='anchor_price', value=313.91, unit='USD/t', label='Anchor')}
    assert check('The anchor is 313.91 USD/t; freight adds 25.5 USD/t [K1].', found, facts=fact).is_valid


@pytest.mark.parametrize('text, says', [
    ('Freight was 25.5 USD/t [K7].', 'Citation [K7] does not match a retrieved passage.'),
    ('Freight was 23.00 USD/t [K1].', 'Number 23 is not grounded in any tool output.'),
    ('Freight eased to 25.5 USD/t on 24 Sep 2027 [K1].', 'Date 24 Sep 2027 is not in any tool output.'),
    ('Freight was 25.5 USD/t in the week of 3 Aug [K1].', 'Date 3 Aug is not in any tool output.'),
    ('The report says "rates eased due to surplus vessel tonnage in the Atlantic basin" at 25.5 USD/t [K1].', 'is not in a retrieved passage'),
    ('According to argus-fob-morocco-30-09-2026.xlsx, freight was 25.5 USD/t [K1].', '"argus-fob-morocco-30-09-2026.xlsx" is named, but none of its passages was retrieved.'),
])
def test_what_is_not_in_a_retrieved_passage_is_refused(knowledge, text, says):
    found = {'K1': retrieved(knowledge)['K1']}
    result = check(text, found, sources=[d.title for d in rag.documents(knowledge.db)])
    assert not result.is_valid and any(says in e for e in result.errors), result.errors


def test_naming_a_document_that_was_retrieved_is_fine(knowledge):
    found = {'K1': retrieved(knowledge)['K1']}
    assert check(f'{FREIGHTS} gives 25.5 USD/t [K1].', found, sources=[d.title for d in rag.documents(knowledge.db)]).is_valid


def test_answers_without_knowledge_are_checked_as_before():
    facts = {'anchor_price': ToolFact(key='anchor_price', value=313.91, unit='USD/t', label='Anchor')}
    assert validate_agent_text('Recommended anchor is 313.91 USD/t.', facts).is_valid
    assert not validate_agent_text('Recommended anchor is 315.00 USD/t.', facts).is_valid
    # A date the engine's flags gave is no longer mistaken for an ungrounded number.
    flags = json.dumps({'flagDetails': [{'detail': 'Prices (data through 21 Apr 2026) vs freight (24 Sep 2026).'}]})
    assert validate_agent_text('Prices stop on 21 Apr 2026; the anchor is 313.91 USD/t.', facts, grounding=flags).is_valid
    assert not validate_agent_text('Prices stop on 22 Apr 2026; the anchor is 313.91 USD/t.', facts, grounding=flags).is_valid


# ───────────────────────── agent loop (the model is mocked) ─────────────────────────

def _reply(message: dict) -> MagicMock:
    return MagicMock(status_code=200, json=lambda: {'choices': [{'message': {'role': 'assistant', **message}}]})


def _search_call(query: str) -> MagicMock:
    return _reply({'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'search_knowledge', 'arguments': json.dumps({'query': query, 'limit': 2})}}]})


def _turn(store, replies: list[MagicMock], text: str = 'Why 25.5 USD/t of freight to Brazil?'):
    async def collect():
        return [e async for e in run_agent_turn(store, store.add_sim('Knowledge').id, text)]
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'mock_key'}), patch('httpx.AsyncClient.post', side_effect=replies) as post:
        return asyncio.run(collect()), post


def test_a_cited_answer_is_streamed_with_its_citations(knowledge):
    events, post = _turn(knowledge, [
        _search_call(QUESTION),
        _reply({'content': 'The latest Jorf Lasfar – Santos rate is 25.5 USD/t, for the week ending 2026-10-01 [K1].'}),
    ])
    assert [e.type for e in events] == ['step', 'step', 'tool', 'citation', 'text', 'done']
    citation, text = events[3].payload, events[4].payload['content']
    assert (citation['index'], citation['label']) == (1, f'{FREIGHTS}, 01-Oct-2026, Phosphates')
    assert text == 'The latest Jorf Lasfar – Santos rate is 25.5 USD/t, for the week ending 2026-10-01 [1].'
    # The model received the passages as the tool's result, and was told how to cite them.
    sent = post.call_args_list[1].kwargs['json']['messages']
    assert 'search_knowledge' in sent[0]['content'] and '[K1]' in sent[0]['content']
    assert json.loads(sent[-1]['content'])['results'][0]['ref'] == 'K1'
    assert knowledge.sim(knowledge.sims()[0][0].id).runs == []  # a question about documents is not a pricing run


def test_an_answer_that_misquotes_twice_is_replaced_by_the_passages(knowledge):
    wrong = _reply({'content': 'CRU reported that freight eased to 23.00 USD/t on 12 Aug 2026 [K1].'})
    events, post = _turn(knowledge, [_search_call(QUESTION), wrong, wrong])
    assert [e.type for e in events] == ['step', 'step', 'tool', 'citation', 'citation', 'text', 'done']
    text = events[5].payload['content']
    assert text.startswith('Here is what the indexed documents say:') and '[1]' in text and '[2]' in text and '23.00' not in text
    assert '| 2026-10-01 | Jorf Lasfar – Santos | 30 | 25.5 |' in text
    # After the first wrong answer the model was told what to correct.
    correction = post.call_args_list[2].kwargs['json']['messages'][-1]['content']
    assert 'Number 23 is not grounded' in correction and 'Date 12 Aug 2026 is not in any tool output' in correction


# ───────────────────────── scripted fallback, over the API ─────────────────────────

def test_without_a_model_a_question_about_the_documents_is_answered_with_the_passages():
    client = TestClient(app)
    client.post('/api/reset')
    sim = client.post('/api/simulations', json={'title': 'Sources'}).json()
    r = client.post(f'/api/simulations/{sim["id"]}/messages', json={'text': 'What do the reports say about freight from Jorf Lasfar to Santos?', 'mode': 'script'})
    events = [e for e in (json.loads(line[5:]) for line in r.text.splitlines() if line.startswith('data:')) if e['type'] != 'job']
    kinds = [e['type'] for e in events]
    assert kinds[:2] == ['step', 'tool'] and kinds[-2:] == ['text', 'done'] and set(kinds[2:-2]) == {'citation'}
    assert events[2]['payload']['label'] == f'{FREIGHTS}, 01-Oct-2026, Phosphates'
    text = events[-2]['payload']['content']
    assert text.startswith('Here is what the indexed documents say:') and '[1]' in text and '[K' not in text
    assert client.get(f'/api/simulations/{sim["id"]}').json()['runs'] == []

    nothing = client.post(f'/api/simulations/{sim["id"]}/messages', json={'text': 'Any document about holiday weather in Paris?', 'mode': 'script'})
    assert 'I found nothing about that in the indexed documents.' in nothing.text and 'event: citation' not in nothing.text


# ───────────────────────── what a real model writes ─────────────────────────
# Answers of nvidia/nemotron-3-super-120b-a12b through OpenRouter, as received: non-breaking hyphens in dates, in the
# product grade and for the minus sign, narrow spaces before units, and 【K1】 for a citation.

DOCUMENT_ANSWER = (
    'The freight data for the Jorf Lasfar → Santos route shows a steady increase week‑over‑week:\n\n'
    '- Week ending 2026‑09‑17: **24.5 USD/t**  \n- Week ending 2026‑09‑24: **25.0 USD/t**  \n- Week ending 2026‑10‑01: **25.5 USD/t**  \n\n'
    'These figures come from the historical freight table in *fertilizer‑week‑historical‑freights‑01‑10‑2026.xlsx* (phosphates section)【K1】. '
    'The upward movement from 24.5 to 25.5 USD/t indicates that freight rates on this lane are **going up**.'
)
PRICING_ANSWER = (
    '**Phosfusion 65‑35 vs. TSP (Reference‑Minus pricing)**  \n\n- **Anchor price (Reference‑Minus)**: **313.91 USD/t**  \n'
    '- **Contribution Gross Margin (CGM)**: **3.02 USD/t**  \n- **TSP CGM (for reference)**: **‑15.18 USD/t**  \n- **Unit cost**: **310.90 USD/t**  \n'
    '- **Cost‑plus floor (20 % margin)**: **373.08 USD/t**  \n\n*All figures come directly from the pricing engine; the human decides on the final price.*'
)
PRICING_FACTS = {k: ToolFact(key=k, value=v, unit='USD/t', label=k) for k, v in
                 {'anchor_price': 313.91, 'cgm': 3.02, 'cgm_ref': -15.18, 'unit_cost': 310.9, 'floor': 373.08}.items()}
PARAMETERS = json.dumps({'parameters': {'costPlusMargin': 0.2, 'valueShare': 0.3333333333333333}})


def test_a_real_answer_about_a_document_passes_and_its_citation_is_found(knowledge):
    found = retrieved(knowledge)
    result = check(DOCUMENT_ANSWER, found, sources=[d.title for d in rag.documents(knowledge.db)])
    assert result.is_valid, result.errors
    text, events = cited(DOCUMENT_ANSWER, found)
    assert '(phosphates section)[1].' in text and '【' not in text
    assert [e.payload['label'] for e in events] == [f'{FREIGHTS}, 01-Oct-2026, Phosphates']
    assert check('Rates on the route moved in a 24.5–25.5 USD/t range, from 24.5-25 USD/t earlier [K1].', found).is_valid  # a range, not a negative
    # The same typography does not let a wrong figure or a wrong date through.
    assert not check(DOCUMENT_ANSWER.replace('25.5', '26.5'), found).is_valid
    assert not check(DOCUMENT_ANSWER.replace('2026‑09‑17', '2026‑08‑17'), found).is_valid


def test_a_real_pricing_answer_passes():
    result = validate_agent_text(PRICING_ANSWER, PRICING_FACTS, grounding=PARAMETERS)
    assert result.is_valid, result.errors
    # 20 % is the 0.2 the tools returned; a share they did not return is refused, and so is a figure with the wrong sign.
    assert validate_agent_text('Value share is 33.3 % of 313.91 USD/t.', PRICING_FACTS, grounding=PARAMETERS).is_valid
    assert not validate_agent_text(PRICING_ANSWER.replace('20 %', '25 %'), PRICING_FACTS, grounding=PARAMETERS).is_valid
    assert not validate_agent_text(PRICING_ANSWER, PRICING_FACTS).is_valid  # without the tool output, 20 % has no source
    assert not validate_agent_text('TSP earns 15.18 USD/t.', PRICING_FACTS).is_valid


def _finished(content: str, reason: str) -> MagicMock:
    return MagicMock(status_code=200, json=lambda: {'choices': [{'finish_reason': reason, 'message': {'role': 'assistant', 'content': content}}]})


def test_an_empty_or_cut_off_answer_is_not_sent_as_the_answer(knowledge):
    good = 'The latest Jorf Lasfar – Santos rate is 25.5 USD/t【K1】.'
    events, post = _turn(knowledge, [_search_call(QUESTION), _finished('', 'length'), _finished(good, 'stop')])
    assert events[-2].payload['content'] == 'The latest Jorf Lasfar – Santos rate is 25.5 USD/t[1].' and events[-3].type == 'citation'
    assert 'Your answer was empty.' in post.call_args_list[2].kwargs['json']['messages'][-1]['content']

    events, post = _turn(knowledge, [_search_call(QUESTION), _finished('The latest Jorf Lasfar – Santos rate is 25.5 USD/t and', 'length'), _finished('', 'stop')])
    assert 'cut off before its end' in post.call_args_list[2].kwargs['json']['messages'][-1]['content']
    assert events[-2].payload['content'].startswith('Here is what the indexed documents say:')  # twice not an answer: the passages
    assert post.call_args.kwargs['json']['max_tokens'] == 3000


# ───────────────────────── when the model stops answering ─────────────────────────

def _refused(status: int) -> MagicMock:
    return MagicMock(status_code=status, json=lambda: {'error': {'code': status}})


def _engine_call() -> MagicMock:
    return _reply({'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'run_engine', 'arguments': '{"product_ids": ["phos-65-35"], "reference_id": "TSP"}'}}]})


def test_a_question_the_script_does_not_know_runs_nothing_when_the_model_is_out(knowledge):
    events, _ = _turn(knowledge, [_refused(429)], text='Hello, how are you today?')
    assert [e.type for e in events] == ['error', 'text', 'done']
    assert events[0].payload == {'message': 'The language model did not answer (the request limit of the OpenRouter account is reached). This reply is made without it.', 'recoverable': True}
    assert events[1].payload['content'].startswith('I can price a product against a reference') and events[2].payload == {'mode': 'script'}
    assert all(sim.runs == [] for sim, _ in knowledge.sims() if sim.title == 'Knowledge')

    events, _ = _turn(knowledge, [_refused(402)], text='Price Phosfusion 65-35 against TSP')  # a pricing is still a pricing
    assert events[0].payload['message'].startswith('The language model did not answer (the OpenRouter account has no credits')
    assert 'question' in [e.type for e in events]  # it starts by asking which TSP cost to use, as the sources disagree


def test_work_done_before_the_model_failed_is_not_done_again(knowledge):
    events, _ = _turn(knowledge, [_engine_call(), _refused(429)], text='Price Phosfusion 65-35 against TSP')
    kinds = [e.type for e in events]
    assert kinds.count('question') == 1 and 'result' not in kinds and kinds[-3:] == ['error', 'text', 'done']  # priced once, as a preview
    assert events[-2].payload['content'].startswith('Recommended anchor: 313.91 USD/t')  # from the run the engine did make
    assert all(not sim.runs for sim, _ in knowledge.sims() if sim.title == 'Knowledge')  # the model saved nothing

    events, _ = _turn(knowledge, [_search_call(QUESTION), ConnectionError('network down')])
    assert [e.type for e in events][-5:] == ['error', 'citation', 'citation', 'text', 'done']
    assert events[-5].payload['message'] == 'The language model did not answer (ConnectionError). This reply is made without it.'
    assert events[-2].payload['content'].startswith('Here is what the indexed documents say:')
