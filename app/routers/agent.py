"""FastAPI router for conversational agent endpoints and SSE streaming."""
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent import (
    apply_staged_change,
    get_budget_status,
    get_staged_change,
    route_turn,
    stream_agent_message,
)
from ..schemas import Run
from ..store import Store, StoreDep

router = APIRouter(tags=['Agent'])


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, description='User message content')
    mode: Optional[Literal['auto', 'llm', 'script']] = 'auto'


class ChangeApplyRequest(BaseModel):
    summary: Optional[str] = None


@router.post(
    '/simulations/{sim_id}/messages',
    summary='Send a message to the agent and receive a Server-Sent Events stream',
    response_class=StreamingResponse,
)
async def post_simulation_message(
    sim_id: str,
    body: AgentMessageRequest,
    store: Store = StoreDep,
):
    """Start an agent turn. Streams step, tool, result, flag, question, change, and text events."""
    # Ensure simulation exists
    store.sim(sim_id)
    force = None if body.mode == 'auto' else body.mode
    generator = stream_agent_message(store, sim_id, body.text, force)
    return StreamingResponse(
        generator,
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post(
    '/changes/{change_id}/apply',
    response_model=Run,
    status_code=201,
    summary='Apply a proposed staged change card to produce the next immutable run version',
)
def apply_change(
    change_id: str,
    body: ChangeApplyRequest = ChangeApplyRequest(),
    store: Store = StoreDep,
):
    change = get_staged_change(change_id)
    if not change:
        raise HTTPException(404, f'Staged change {change_id!r} not found or expired')
    sim_id = change['simulationId']
    summary = body.summary or f'Applied: {change["label"]}'
    return apply_staged_change(store, sim_id, change['patch'], summary=summary)


@router.post(
    '/changes/{change_id}/dismiss',
    status_code=204,
    summary='Dismiss a proposed staged change card without applying',
)
def dismiss_change(change_id: str):
    change = get_staged_change(change_id)
    if not change:
        raise HTTPException(404, f'Staged change {change_id!r} not found or expired')
    change['status'] = 'dismissed'
    return None


@router.get('/agent/status', summary='Current agent health, active model, and budget tracking')
def agent_status():
    budget = get_budget_status()
    active_mode = route_turn()
    return {
        'mode': active_mode,
        'budget': budget,
    }

