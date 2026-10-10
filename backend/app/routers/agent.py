"""FastAPI router for conversational agent endpoints and SSE streaming."""
import asyncio
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
from ..agent.fallback import next_prompts, start_prompts, supported_commands
from ..agent.router import agent_state
from ..agent import jobs
from ..schemas import Job, Run, RunInputPatch
from ..store import Store, StoreDep

router = APIRouter(tags=['Agent'])


class AgentAnswer(BaseModel):
    """The option picked on a `question` event. `resume` and `summary` are sent back as that event gave them."""
    option: str
    question: Optional[str] = None
    resume: Optional[dict] = None
    summary: Optional[str] = None


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, description='User message content')
    mode: Optional[Literal['auto', 'llm', 'script']] = 'auto'
    input: Optional[RunInputPatch] = Field(None, description='Price this run input (Configure run form) instead of reading `text`')  # type: ignore[valid-type]
    answer: Optional[AgentAnswer] = None


class ChangeApplyRequest(BaseModel):
    summary: Optional[str] = None


@router.post(
    '/simulations/{sim_id}/messages',
    summary='Send a message to the agent: starts a job and streams its events (Server-Sent Events)',
    response_class=StreamingResponse,
)
async def post_simulation_message(sim_id: str, body: AgentMessageRequest, store: Store = StoreDep):
    """Starts an agent job and follows it. The first and the last event are `job`, with its id and state.

    The job belongs to the server, not to this response: closing the stream does not stop it. Its state is at
    `GET /api/jobs/{id}` (the id is also in the `X-Job-Id` header), and stays there after it ends.
    """
    store.sim(sim_id)  # 404 before anything starts
    force = None if body.mode == 'auto' else body.mode
    job = jobs.start(
        store, sim_id, body.text, force,
        input=body.input.model_dump(exclude_unset=True, mode='json') if body.input is not None else None,
        answer=body.answer.model_dump() if body.answer else None,
    )
    return StreamingResponse(
        jobs.follow(job.id),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no', 'X-Job-Id': job.id},
    )


@router.get('/jobs/{job_id}', response_model=Job, summary='An agent job and the state it is in')
def get_job(job_id: str, store: Store = StoreDep):
    row = jobs.get(store, job_id)
    if row is None:
        raise HTTPException(404, f'Job {job_id!r} not found')
    return jobs.view(row)


@router.post('/jobs/{job_id}/cancel', response_model=Job, summary='Stop a job that has not ended')
async def cancel_job(job_id: str, store: Store = StoreDep):
    row = jobs.get(store, job_id)
    if row is None:
        raise HTTPException(404, f'Job {job_id!r} not found')
    jobs.cancel(store, row)
    await asyncio.sleep(0)  # let a running job write its own end
    store.db.refresh(row)
    return jobs.view(row)


@router.get('/simulations/{sim_id}/jobs', response_model=list[Job], summary='The agent jobs of a simulation, newest first')
def list_jobs(sim_id: str, store: Store = StoreDep):
    store.sim(sim_id)
    return [jobs.view(r) for r in jobs.history(store, sim_id)]


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


@router.get('/agent/prompts', summary='Example requests the agent understands: to start with, and once a simulation has a run')
def agent_prompts(store: Store = StoreDep):
    return {'start': start_prompts(store), 'next': next_prompts(store), 'supported': supported_commands(store)}


@router.get('/agent/status', summary='Current agent health, active model, and budget tracking')
def agent_status():
    return {**agent_state(), 'budget': get_budget_status()}

