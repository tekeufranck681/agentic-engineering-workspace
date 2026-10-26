"""ENG-032: live SSE stream of persisted run events.

Endpoint: ``GET /runs/{run_id}/events/stream`` — a ``text/event-stream`` that
first replays the persisted backlog (every event with a sequence > the resume
token) and then tails new events until the run reaches a terminal state.

Reconnect contract:

* Every event carries ``id: <sequence>`` — the standard SSE *Last-Event-ID*
  token. Browser ``EventSource`` sends ``Last-Event-ID`` automatically on
  reconnect; that header takes precedence;
* non-browser clients can pass the same value as the ``after`` query param
  (useful for SSE clients that cannot set headers);
* events are persisted first (ENG-027), so a client that disconnects and
  resumes loses nothing: replay always comes from the database, never from
  an in-memory buffer.

Keep-alive: comment heartbeats (``: keep-alive``) prevent idle proxies from
cutting the connection when nothing is happening.

Backpressure/polling policy (MVP, documented honestly): the loop polls the
database every ``SSE_POLL_INTERVAL_SECONDS``. PostgreSQL LISTEN/NOTIFY is the
planned upgrade; polling is correct even without it, just coarser.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.enums import RunStatus
from app.modules.persistence.run_models import RunEventRow
from app.modules.persistence.run_store import RunStore

SSE_POLL_INTERVAL_SECONDS = 0.5
SSE_HEARTBEAT_EVERY_TICKS = 30  # heartbeat when idle for ~interval*ticks

TERMINAL_RUN_STATUSES = {
    RunStatus.succeeded.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
}

router = APIRouter(prefix="/runs", tags=["runs"])


def format_sse(event: RunEventRow) -> str:
    """One SSE frame: id (resume token), event type, JSON payload."""
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(event.payload, separators=(',', ':'))}\n\n"
    )


async def _event_stream(
    store: RunStore, run_id: str, after: int
) -> AsyncGenerator[str, None]:
    last_sent = after
    idle_ticks = 0
    while True:
        for event in store.events_since(run_id, last_sent):
            yield format_sse(event)
            last_sent = event.sequence
            idle_ticks = 0

        status = store.get_run_status(run_id)
        if status in TERMINAL_RUN_STATUSES:
            yield "event: run_finished\ndata: " + json.dumps(
                {"run_id": run_id, "status": status}, separators=(",", ":")
            ) + "\n\n"
            return

        idle_ticks += 1
        if idle_ticks >= SSE_HEARTBEAT_EVERY_TICKS:
            yield ": keep-alive\n\n"
            idle_ticks = 0
        await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)


@router.get("/{run_id}/events/stream")
async def stream_run_events(
    run_id: str,
    session: Session = Depends(get_session),
    after: int = 0,
    last_event_id: str | None = Header(default=None),
) -> StreamingResponse:
    """Stream all persisted events for `run_id`, resumable after disconnect."""
    store = RunStore(session)
    if store.get_run_status(run_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")

    resume_from = int(last_event_id) if last_event_id is not None else after
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # don't buffer SSE behind nginx/reverse proxies
    }
    return StreamingResponse(
        _event_stream(store, run_id, resume_from),
        media_type="text/event-stream",
        headers=headers,
    )
