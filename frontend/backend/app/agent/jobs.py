"""Agent jobs: every turn of the agent is a job with a state that is stored, not guessed.

    queued → running → completed | failed | cancelled | timed_out

A job runs as a task of the server, not of the request that asked for it: the browser follows it as Server-Sent Events,
and a page that is reloaded reads the stored state (GET /jobs/{id}) instead. A job cannot stay "running": it is ended
as `timed_out` after AGENT_JOB_TIMEOUT_SECONDS, and one the server lost (a restart) is ended the first time it is read.
Its id is the correlation id of everything the server logs about it.
"""
import asyncio
import contextvars
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from sqlalchemy import select

from .. import db
from ..db import JobRow
from ..store import Store
from .service import agent_events

TIMEOUT_SECONDS = float(os.getenv('AGENT_JOB_TIMEOUT_SECONDS', '120'))
LOST_AFTER = timedelta(seconds=30)  # past the timeout with no end written: the server that ran it is gone
TERMINAL = ('completed', 'failed', 'cancelled', 'timed_out')
log = logging.getLogger('evs.jobs')


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _Live:
    """A job this process is running: the frames sent so far, for whoever follows it."""
    def __init__(self) -> None:
        self.frames: list[str] = []
        self.done = False
        self.changed = asyncio.Condition()
        self.task: Optional[asyncio.Task] = None


_live: dict[str, _Live] = {}
# The job a piece of code is running for: every log line of the app made inside it carries this id (see main.py).
current_job: contextvars.ContextVar[str] = contextvars.ContextVar('evs_job', default='-')


def view(row: JobRow) -> dict[str, Any]:
    iso = lambda d: (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat() if d else None  # SQLite gives the time back without its zone
    return {
        'id': row.id, 'simulationId': row.simulationId, 'kind': row.kind, 'state': row.state, 'mode': row.mode,
        'request': row.request, 'result': row.result, 'failureCode': row.failureCode, 'error': row.error,
        'transitions': row.transitions, 'createdAt': iso(row.createdAt), 'startedAt': iso(row.startedAt), 'finishedAt': iso(row.finishedAt),
        'timeoutSeconds': TIMEOUT_SECONDS,
    }


def _move(session, row: JobRow, state: str, **fields: Any) -> None:
    """One transition, written at once: what is stored is what happened."""
    at = _now()
    row.state = state
    row.transitions = [*row.transitions, {'state': state, 'at': at.isoformat()}]
    if state == 'running':
        row.startedAt = at
    if state in TERMINAL:
        row.finishedAt = at
    for k, v in fields.items():
        setattr(row, k, v)
    session.commit()
    log.info('job=%s sim=%s state=%s%s', row.id, row.simulationId, state, f' code={row.failureCode}' if row.failureCode else '')


def _frame(row: JobRow) -> str:
    return f'event: job\ndata: {json.dumps({"id": f"job_{row.id}", "type": "job", "payload": view(row)}, separators=(",", ":"))}\n\n'


def _error_frame(message: str, code: str) -> str:
    return f'event: error\ndata: {json.dumps({"id": f"error_{uuid4().hex[:8]}", "type": "error", "payload": {"message": message, "code": code, "fatal": True}}, separators=(",", ":"))}\n\n'


async def _publish(live: _Live, frame: str) -> None:
    async with live.changed:
        live.frames.append(frame)
        live.changed.notify_all()


async def _work(job_id: str, live: _Live, force_mode: Optional[str]) -> None:
    current_job.set(job_id)
    with db.SessionLocal() as session:
        row = session.get(JobRow, job_id)
        store = Store(session)
        request = row.request
        version: Optional[int] = None
        outcome, mode, failure = 'answer', None, None
        try:
            _move(session, row, 'running')
            await _publish(live, _frame(row))
            async with asyncio.timeout(TIMEOUT_SECONDS):
                async for event in agent_events(store, row.simulationId, request['text'], force_mode, request.get('input'), request.get('answer')):
                    if event.type == 'result':
                        version, outcome = event.payload.get('version'), 'run'
                    elif event.type in ('question', 'change') and outcome != 'run':
                        outcome = event.type
                    elif event.type == 'text' and event.payload.get('code') == 'unsupported_request':
                        outcome = 'unsupported'
                    elif event.type == 'error' and event.payload.get('fatal'):
                        failure = (event.payload.get('code') or 'request_failed', event.payload.get('message') or 'The request failed')
                    elif event.type == 'done':
                        mode = event.payload.get('mode')
                    await _publish(live, f'event: {event.type}\ndata: {json.dumps(event.model_dump(), separators=(",", ":"))}\n\n')
            if failure:
                _move(session, row, 'failed', mode=mode, failureCode=failure[0], error=failure[1])
            else:
                _move(session, row, 'completed', mode=mode, result={'outcome': outcome, 'runVersion': version})
        except TimeoutError:
            session.rollback()
            message = f'No answer after {TIMEOUT_SECONDS:g} seconds, so the request was stopped. Nothing was left half done: try it again.'
            _move(session, row, 'timed_out', failureCode='timed_out', error=message)
            await _publish(live, _error_frame(message, 'timed_out'))
        except asyncio.CancelledError:
            session.rollback()
            _move(session, row, 'cancelled', failureCode='cancelled', error='The request was cancelled.')
            await asyncio.shield(_publish(live, _error_frame('The request was cancelled.', 'cancelled')))
        except Exception:
            session.rollback()
            # The cause goes to the log with the job id. The user gets words that are safe to show, and the same id.
            log.exception('job=%s sim=%s failed', job_id, row.simulationId)
            message = f'The server could not complete this request. Quote job {job_id} to find the cause in its logs.'
            _move(session, row, 'failed', failureCode='internal_error', error=message)
            await _publish(live, _error_frame(message, 'internal_error'))
        finally:
            await asyncio.shield(_publish(live, _frame(row)))
            async with live.changed:
                live.done = True
                live.changed.notify_all()
            asyncio.get_running_loop().call_later(60, _live.pop, job_id, None)


def start(store: Store, simulation_id: str, text: str, force_mode: Optional[str] = None,
          input: Optional[dict] = None, answer: Optional[dict] = None) -> JobRow:
    """Store the job (queued) and start it. Must be called from the server's event loop."""
    request = {'text': text, **({'input': input} if input is not None else {}), **({'answer': answer} if answer else {})}
    row = JobRow(id=f'j{uuid4().hex[:12]}', simulationId=simulation_id, kind='run' if input is not None else 'answer' if answer else 'message',
                 state='queued', request=json.loads(json.dumps(request, default=str)), transitions=[], createdAt=_now())
    store.db.add(row)
    _move(store.db, row, 'queued')
    live = _live[row.id] = _Live()
    live.task = asyncio.create_task(_work(row.id, live, force_mode))
    return row


async def follow(job_id: str) -> AsyncIterator[str]:
    """The job's events from its first one, then as they come, until it ends. Leaving early does not stop the job."""
    live = _live.get(job_id)
    if live is None:
        return
    sent = 0
    while True:
        async with live.changed:
            await live.changed.wait_for(lambda: len(live.frames) > sent or live.done)
            frames, done = live.frames[sent:], live.done
        for frame in frames:
            yield frame
        sent += len(frames)
        if done and sent >= len(live.frames):
            return


def settle(store: Store, row: JobRow) -> JobRow:
    """End a job that can no longer end by itself: past its timeout, and not running in this server."""
    if row.state not in TERMINAL and row.id not in _live:
        created = row.createdAt if row.createdAt.tzinfo else row.createdAt.replace(tzinfo=timezone.utc)
        if _now() - created > timedelta(seconds=TIMEOUT_SECONDS) + LOST_AFTER:
            _move(store.db, row, 'timed_out', failureCode='lost', error='The server stopped before this request finished. Nothing was left half done: try it again.')
    return row


def get(store: Store, job_id: str) -> Optional[JobRow]:
    row = store.db.get(JobRow, job_id)
    if row is not None:
        store.db.refresh(row)  # another session may have moved it
        settle(store, row)
    return row


def latest(store: Store, simulation_id: str) -> Optional[JobRow]:
    row = store.db.scalars(select(JobRow).where(JobRow.simulationId == simulation_id).order_by(JobRow.createdAt.desc()).limit(1)).first()
    if row is not None:
        store.db.refresh(row)
        settle(store, row)
    return row


def history(store: Store, simulation_id: str, limit: int = 20) -> list[JobRow]:
    rows = list(store.db.scalars(select(JobRow).where(JobRow.simulationId == simulation_id).order_by(JobRow.createdAt.desc()).limit(limit)))
    return [settle(store, r) for r in rows]


def cancel(store: Store, row: JobRow) -> JobRow:
    """Stop a job that has not ended. One that already has is returned as it is."""
    live = _live.get(row.id)
    if row.state in TERMINAL:
        return row
    if live and live.task and not live.task.done():
        live.task.cancel()  # the task writes the state itself
    else:
        _move(store.db, row, 'cancelled', failureCode='cancelled', error='The request was cancelled.')
    return row
