"""Async agent loop (router → llm ⇄ tools → checker → template)."""
import asyncio
import json
import os
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx

from ..rag import documents
from ..store import Store
from .checker import ValidationResult, render_fallback_template, validate_agent_text
from .citations import cited, knowledge_answer
from .fallback import run_scripted_turn
from .router import get_openrouter_api_key, record_llm_failure, record_llm_success
from .tools import (
    TOOL_DEFINITIONS,
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
    tool_search_knowledge,
    tool_snapshot_view,
    tool_stage_change,
)
from .types import AgentEvent, AgentMessage, AgentState, ToolFact

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
DEFAULT_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-sonnet-5.5')
# Without a limit OpenRouter reserves the model's largest answer (65,536 tokens for Claude Sonnet) and refuses the
# request, with 402, on an account that cannot pay for one. The agent's answers and tool calls are short.
# A model that reasons before it answers spends part of the limit on that.
MAX_TOKENS = int(os.getenv('OPENROUTER_MAX_TOKENS', '3000'))

SYSTEM_PROMPT = """You are the Eco Value Simulator pricing agent for OCP Nutricrops Green Solutions.
Your role: gather, check, and explain economic assessment for new fertilizer products (e.g. Phosfusion vs TSP).

CRITICAL RULES:
1. THE CODE CALCULATES. THE HUMAN DECIDES. YOU EXPLAIN.
2. NEVER calculate numbers or margins yourself. All numbers must come from engine tools.
3. When prices, costs, or margins are quoted, always mention the unit (USD/t).
4. Do not apply input changes directly: propose them using the `stage_change` tool.
5. If the user must choose between options (e.g. Netback vs FOB), use the `ask_user` tool with option chips.
6. Tone: concise, professional, direct, units on every figure. Never invent numbers.
7. KNOWLEDGE: when explaining WHY a price, freight rate or yield assumption was chosen, or when asked what a report,
   study or document says, call `search_knowledge` first and use only what the returned passages say.
   Cite every passage you use with its ref in square brackets, e.g. [K1]. Never name a report, a date or a quotation
   that is not in the retrieved passages; if they do not answer the question, say so.
   Figures used in a calculation still come from the engine tools, not from passages.
"""


def _uid(prefix: str = 'e') -> str:
    return f'{prefix}_{uuid4().hex[:8]}'


async def run_agent_turn(
    store: Store,
    simulation_id: str,
    user_text: str,
    history: list[dict[str, Any]] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Execute one turn of the agent loop with tool execution and numeric verification."""
    api_key = get_openrouter_api_key()
    if not api_key:
        async for event in run_scripted_turn(store, simulation_id, user_text):
            yield event
        return

    messages: list[dict[str, Any]] = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({'role': 'user', 'content': user_text})

    facts: dict[str, ToolFact] = {}
    citations: dict[str, dict[str, Any]] = {}  # passages retrieved this turn, by ref
    grounding: list[str] = []  # everything the tools returned this turn: dates and quotations are checked against it
    max_steps = 8
    retries = 0

    async def unavailable(reason: str) -> AsyncIterator[AgentEvent]:
        """The model did not answer: say so, then finish the turn without it.

        What the tools already did in this turn stays done (a run is not priced a second time): the answer is made
        from their results. A turn that had not started goes to the scripted fallback.
        """
        record_llm_failure()
        yield AgentEvent(id=_uid('error'), type='error', payload={
            'message': f'The language model did not answer ({reason}). This reply is made without it.', 'recoverable': True,
        })
        if citations and not facts:
            content, citation_events = cited(knowledge_answer(list(citations.values())), citations)
            for ce in citation_events:
                yield ce
            yield AgentEvent(id=_uid('text'), type='text', payload={'content': content})
        elif facts:
            yield AgentEvent(id=_uid('text'), type='text', payload={'content': render_fallback_template(facts)})
        else:
            async for event in run_scripted_turn(store, simulation_id, user_text):
                yield event
            return
        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'script'})

    headers = {
        'Authorization': f'Bearer {api_key}',
        'HTTP-Referer': 'http://localhost:5173',
        'X-Title': 'Eco Value Simulator',
        'Content-Type': 'application/json',
    }

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            for step_idx in range(max_steps):
                payload = {
                    'model': DEFAULT_MODEL,
                    'messages': messages,
                    'tools': TOOL_DEFINITIONS,
                    'temperature': 0.0,
                    'max_tokens': MAX_TOKENS,
                }
                resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                if resp.status_code != 200:
                    reason = {402: 'the OpenRouter account has no credits for this request', 429: 'the request limit of the OpenRouter account is reached'}
                    async for event in unavailable(reason.get(resp.status_code, f'HTTP {resp.status_code}')):
                        yield event
                    return

                res_json = resp.json()
                record_llm_success(estimated_cost=0.005)
                choice = res_json['choices'][0]['message']
                tool_calls = choice.get('tool_calls')

                # Case 1: Model called one or more tools
                if tool_calls:
                    messages.append(choice)
                    for call in tool_calls:
                        fn = call['function']
                        fn_name = fn['name']
                        call_id = call['id']
                        try:
                            args = json.loads(fn['arguments'] or '{}')
                        except json.JSONDecodeError:
                            args = {}

                        yield AgentEvent(
                            id=_uid('step'),
                            type='step',
                            payload={'label': f'Calling {fn_name}...', 'status': 'running'},
                        )

                        tool_data: dict[str, Any] = {}
                        tool_events: list[AgentEvent] = []

                        if fn_name in ('run_engine', 'run_pricing'):
                            tool_data, tool_facts, tool_events = tool_run_engine(
                                store=store,
                                simulation_id=simulation_id,
                                product_ids=args.get('product_ids'),
                                reference_id=args.get('reference_id'),
                                overrides=args.get('overrides'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'read_inputs':
                            tool_data, tool_facts, tool_events = tool_read_inputs(
                                store=store,
                                simulation_id=simulation_id,
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'check_inputs':
                            tool_data, tool_facts, tool_events = tool_check_inputs(
                                store=store,
                                simulation_id=simulation_id,
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'compare_runs':
                            tool_data, tool_facts, tool_events = tool_compare_runs(
                                store=store,
                                simulation_id=simulation_id,
                                run_id_a=args.get('run_id_a'),
                                run_id_b=args.get('run_id_b'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'snapshot_view':
                            tool_data, tool_facts, tool_events = tool_snapshot_view(
                                store=store,
                                simulation_id=simulation_id,
                                snapshot_id=args.get('snapshot_id', '2024'),
                                product_ids=args.get('product_ids'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'draft_memo':
                            tool_data, tool_facts, tool_events = tool_draft_memo(
                                store=store,
                                simulation_id=simulation_id,
                                run_id=args.get('run_id'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'explain_flags':
                            tool_data, tool_facts, tool_events = tool_explain_flags(
                                store=store,
                                simulation_id=simulation_id,
                                flag_codes=args.get('flag_codes'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'explain_run':
                            tool_data, tool_facts, tool_events = tool_explain_run(
                                store=store,
                                simulation_id=simulation_id,
                                question=args.get('question'),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'run_sulphur_sensitivity':
                            tool_data, tool_facts, tool_events = tool_run_sulphur_sensitivity(
                                store=store,
                                product_id=args.get('product_id', 'phos-65-35'),
                                reference_id=args.get('reference_id', 'TSP'),
                                from_price=float(args.get('from_price', 100.0)),
                                to_price=float(args.get('to_price', 1000.0)),
                                step=float(args.get('step', 50.0)),
                            )
                            for tf in tool_facts:
                                facts[tf.key] = tf
                        elif fn_name == 'search_knowledge':
                            # In a thread: the query is embedded over the network, which would hold up every other request.
                            tool_data, tool_facts, tool_events = await asyncio.to_thread(
                                tool_search_knowledge,
                                store=store,
                                query=args.get('query', ''),
                                doc_type=args.get('doc_type'),
                                limit=int(args.get('limit', 4)),
                                first_ref=len(citations) + 1,
                            )
                            citations.update({r['ref']: r for r in tool_data['results']})
                        elif fn_name == 'stage_change':
                            change_obj, tool_events = tool_stage_change(
                                store=store,
                                simulation_id=simulation_id,
                                patch=args.get('patch', {}),
                                label=args.get('label', 'Proposed change'),
                                reason=args.get('reason', ''),
                            )
                            tool_data = change_obj.model_dump()
                        elif fn_name == 'ask_user':
                            tool_data, tool_events = tool_ask_user(
                                question=args.get('question', ''),
                                options=args.get('options', []),
                            )

                        for te in tool_events:
                            yield te

                        grounding.append(json.dumps(tool_data, ensure_ascii=False))
                        messages.append({
                            'role': 'tool',
                            'tool_call_id': call_id,
                            'content': json.dumps(tool_data),
                        })

                        # If tool was interruptive (ask_user or stage_change), end turn now
                        if fn_name in ('ask_user', 'stage_change'):
                            yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'llm'})
                            return

                    continue

                # Case 2: Model emitted a text message
                text_content = choice.get('content') or ''
                val_result = validate_agent_text(
                    text_content, facts, citations=citations, grounding=' '.join(grounding),
                    sources=[d.title for d in documents(store.db)] if citations else (),
                )
                # Not an answer: nothing at all, or one cut off at the token limit (a reasoning model can spend it all thinking).
                if not text_content.strip():
                    val_result = ValidationResult(False, ['Your answer was empty.'])
                elif res_json['choices'][0].get('finish_reason') == 'length':
                    val_result = ValidationResult(False, ['Your answer was cut off before its end. Answer in fewer words.'])

                if val_result.is_valid:
                    text_content, citation_events = cited(text_content, citations)
                    for ce in citation_events:
                        yield ce
                    yield AgentEvent(id=_uid('text'), type='text', payload={'content': text_content})
                    yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'llm'})
                    return
                else:
                    retries += 1
                    if retries < 2:
                        err_feedback = 'Your response could not be verified: ' + ' '.join(val_result.errors)
                        messages.append({'role': 'assistant', 'content': text_content})
                        messages.append({'role': 'user', 'content': f'Correction needed: {err_feedback} Only state numbers, dates, sources and quotations that are in the tool outputs.'})
                        continue
                    else:
                        # Exceeded retries: emit verified template. A turn that only searched the documents has no
                        # engine facts to fill it with: it gets the passages themselves.
                        if citations and not facts:
                            safe_text, citation_events = cited(knowledge_answer(list(citations.values())), citations)
                            for ce in citation_events:
                                yield ce
                        else:
                            safe_text = render_fallback_template(facts)
                        yield AgentEvent(id=_uid('text'), type='text', payload={'content': safe_text})
                        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'llm'})
                        return

    except Exception as e:
        async for event in unavailable(f'{type(e).__name__}'):
            yield event

