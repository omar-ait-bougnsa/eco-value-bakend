"""Agent service: manages turn executions and Server-Sent Event (SSE) streaming."""
import json
from typing import AsyncIterator, Literal, Optional

from ..schemas import Run, RunInput
from ..store import Store
from .fallback import run_scripted_turn
from .loop import run_agent_turn
from .router import get_budget_status, route_turn
from .types import AgentEvent

# In-memory registry of active staged changes
_staged_changes_registry: dict[str, dict] = {}


def register_staged_change(change_id: str, change_dict: dict) -> None:
    _staged_changes_registry[change_id] = change_dict


def get_staged_change(change_id: str) -> Optional[dict]:
    return _staged_changes_registry.get(change_id)


def sse_format(event: AgentEvent) -> str:
    """Format an AgentEvent into a standard SSE wire frame."""
    payload_json = json.dumps(event.model_dump(), separators=(',', ':'))
    return f'event: {event.type}\ndata: {payload_json}\n\n'


async def stream_agent_message(
    store: Store,
    simulation_id: str,
    user_text: str,
    force_mode: Optional[str] = None,
) -> AsyncIterator[str]:
    """Execute turn and stream Server-Sent Events to the client."""
    selected_mode = route_turn(force_mode)

    if selected_mode == 'llm':
        async for event in run_agent_turn(store, simulation_id, user_text):
            if event.type == 'change':
                register_staged_change(event.payload['id'], event.payload)
            yield sse_format(event)
    else:
        async for event in run_scripted_turn(store, simulation_id, user_text):
            if event.type == 'change':
                register_staged_change(event.payload['id'], event.payload)
            yield sse_format(event)


def apply_staged_change(
    store: Store,
    simulation_id: str,
    patch: dict,
    summary: str = 'Applied proposed change',
) -> Run:
    """Apply an approved staged change and produce an immutable new run version."""
    sim = store.sim(simulation_id)
    prev = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None
    input_data = store.make_input(patch, prev)
    return store.add_run(sim, input_data, by='agent', summary=summary)

