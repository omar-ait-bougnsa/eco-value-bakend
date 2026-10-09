"""Scripted demo runner (deterministic fallback without LLM or external network)."""
import re
from typing import Any, AsyncIterator
from uuid import uuid4

from ..store import Store
from .tools import (
    tool_ask_user,
    tool_check_inputs,
    tool_run_engine,
    tool_run_pricing,
    tool_run_sulphur_sensitivity,
    tool_stage_change,
)
from .types import AgentEvent


def _uid(prefix: str = 'e') -> str:
    return f'{prefix}_{uuid4().hex[:8]}'


async def run_scripted_turn(
    store: Store,
    simulation_id: str,
    user_text: str,
) -> AsyncIterator[AgentEvent]:
    """Execute a deterministic turn matching the doc 09 & doc 10 hero script."""
    text = user_text.lower().strip()

    # 1. Sensitivity intent
    if re.search(r'sensitivity|sensibilit|break-even|seuil|sulphur|soufre', text):
        yield AgentEvent(id=_uid('step'), type='step', payload={'label': 'Running sulphur price sensitivity...', 'status': 'running'})
        data, facts, events = tool_run_sulphur_sensitivity(store, 'phos-65-35', 'TSP', 100.0, 1000.0, 50.0)
        for e in events:
            yield e

        yield AgentEvent(
            id=_uid('text'),
            type='text',
            payload={
                'content': (
                    'Sulphur sensitivity analysis (100 → 1,000 USD/t):\n\n'
                    '• **Phosfusion 65-35 Zero-Margin Break-Even:** 918.86 USD/t\n'
                    '• **TSP Zero-Margin Break-Even:** 870.41 USD/t\n'
                    '• **Parity Crossover Price:** 848.46 USD/t (below 848.46 USD/t, Phosfusion yields higher margin than TSP).'
                ),
            },
        )
        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'script'})
        return

    # 2. What-if value share intent
    val_match = re.search(r'value\s*share.*?(\d+)|share.*?(\d+)|part.*?(\d+)', text)
    if val_match:
        pct_val = int(val_match.group(1) or val_match.group(2) or val_match.group(3))
        frac = pct_val / 100.0
        yield AgentEvent(id=_uid('step'), type='step', payload={'label': f'Staging what-if for value share {pct_val}%...', 'status': 'running'})
        change, events = tool_stage_change(
            store=store,
            simulation_id=simulation_id,
            patch={'valueShare': frac},
            label=f'Value share {pct_val}%',
            reason=f'Test agronomic value capture increase to {pct_val}%',
        )
        for e in events:
            yield e

        yield AgentEvent(
            id=_uid('text'),
            type='text',
            payload={
                'content': f'I have prepared a staged change card with **value share at {pct_val}%**. Click **Apply & re-run** to create version 2.',
            },
        )
        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'script'})
        return

    # 3. Check inputs / Gaps intent
    if re.search(r'check|gap|donn|data', text):
        data, facts, events = tool_check_inputs(store, simulation_id)
        for e in events:
            yield e
        yield AgentEvent(
            id=_uid('text'),
            type='text',
            payload={'content': 'Workspace audit complete. Flags and open items have been surfaced in the thread.'},
        )
        yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'script'})
        return

    # 4. Hero pricing intent (Default or "price phosfusion against tsp")
    yield AgentEvent(id=_uid('step'), type='step', payload={'label': 'Reading CRU market prices (TSP CFR Brazil)...', 'status': 'running'})
    yield AgentEvent(id=_uid('step'), type='step', payload={'label': 'Reading CRU freight (Morocco → Brazil, 45-50k mt)...', 'status': 'running'})
    yield AgentEvent(id=_uid('step'), type='step', payload={'label': 'Resolving raw material costs and reference netback...', 'status': 'done'})

    # Netback confirmation question
    _, q_events = tool_ask_user(
        question='TSP CFR Brazil is 665 USD/t and freight is 23 USD/t. Calculate FOB-equivalent netback (642 USD/t) or use FOB Morocco Spot (699 USD/t)?',
        options=[
            {'id': 'netback', 'label': 'Use Netback (642 USD/t) · (Recommended)', 'sub': 'CFR Brazil minus sea freight'},
            {'id': 'fob', 'label': 'Use FOB Morocco (699 USD/t)', 'sub': 'Direct Moroccan export spot quote'},
        ],
    )
    for qe in q_events:
        yield qe

    # Run the pricing calculation
    data, facts, p_events = tool_run_engine(store, simulation_id, ['phos-65-35'], 'TSP')
    for pe in p_events:
        yield pe

    # Surface flags W1 and P1
    check_data, _, c_events = tool_check_inputs(store, simulation_id)
    for ce in c_events:
        yield ce

    yield AgentEvent(
        id=_uid('text'),
        type='text',
        payload={
            'content': (
                '**Recommended anchor: 313.91 USD/t (Reference-minus)**.\n\n'
                '• That is below the cost-plus floor of **373.08 USD/t**, so margin is tight.\n'
                '• At this price, Phosfusion 65-35 earns **3.02 USD/t CGM** against TSP’s **-15.18 USD/t**.\n'
                '• Value pricing allows up to **740.99 USD/t** if 33.3% of the **302.96 USD/t** crop value is shared.\n\n'
                '*Note: Open item W1 applies — yield gain (0.12) is labelled “%” in the workbook but treated as t/ha.*'
            ),
        },
    )
    yield AgentEvent(id=_uid('done'), type='done', payload={'mode': 'script'})

