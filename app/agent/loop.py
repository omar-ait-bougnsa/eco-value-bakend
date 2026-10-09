"""Async agent loop (router → llm ⇄ tools → checker → template)."""
import json
import os
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx

from ..store import Store
from .checker import render_fallback_template, validate_agent_text
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
    tool_snapshot_view,
    tool_stage_change,
)
from .types import AgentEvent, AgentMessage, AgentState, ToolFact

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
DEFAULT_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')

SYSTEM_PROMPT = """You are the Eco Value Simulator pricing agent for OCP Nutricrops Green Solutions.
Your role: gather, check, and explain economic assessment for new fertilizer products (e.g. Phosfusion vs TSP).

CRITICAL RULES:
1. THE CODE CALCULATES. THE HUMAN DECIDES. YOU EXPLAIN.
2. NEVER calculate numbers or margins yourself. All numbers must come from engine tools.
3. When prices, costs, or margins are quoted, always mention the unit (USD/t).
4. Do not apply input changes directly: propose them using the `stage_change` tool.
5. If the user must choose between options (e.g. Netback vs FOB), use the `ask_user` tool with option chips.
6. Tone: concise, professional, direct, units on every figure. Never invent numbers.
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
    max_steps = 8
    retries = 0

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
                }
                resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                if resp.status_code != 200:
                    record_llm_failure()
                    # Fallback to scripted mode on API error
                    async for event in run_scripted_turn(store, simulation_id, user_text):
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
                val_result = validate_agent_text(text_content, facts)

                if val_result.is_valid:
                    yield AgentEvent(id=_uid('text'), type='text', payload={'content': text_content})
                    yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'llm'})
                    return
                else:
                    retries += 1
                    if retries < 2:
                        err_feedback = 'Your response contained ungrounded numbers: ' + '; '.join(val_result.errors)
                        messages.append({'role': 'assistant', 'content': text_content})
                        messages.append({'role': 'user', 'content': f'Correction needed: {err_feedback}. Only quote numbers from tool outputs.'})
                        continue
                    else:
                        # Exceeded retries: emit verified template
                        safe_text = render_fallback_template(facts)
                        yield AgentEvent(id=_uid('text'), type='text', payload={'content': safe_text})
                        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'llm'})
                        return

    except Exception:
        record_llm_failure()
        async for event in run_scripted_turn(store, simulation_id, user_text):
            yield event

