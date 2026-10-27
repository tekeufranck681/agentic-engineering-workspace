"""Read-only delivery traceability (MVP lock §58: GET /projects/{id}/traceability).

Rebuilds each run's `Delivery` from the append-only events DeliveryService
writes (delivery.started → delivery.gates_passed → delivery.pr_opened). Only
runs persisted for the project are considered, and a run's delivery events
must name that run's task, because run_events are keyed by run id alone.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.enums import ArtifactKind
from app.domain.run import Run
from app.modules.delivery.service import Delivery, EvidenceRef
from app.modules.persistence.errors import ProjectNotFoundError
from app.modules.persistence.repository import get_project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_models import RunEventRow
from app.modules.persistence.run_store import RunStore

router = APIRouter(tags=["delivery"])


class TraceabilityResponse(BaseModel):
    deliveries: list[Delivery]


def delivery_from_events(run: Run, events: list[RunEventRow]) -> Delivery | None:
    """The latest completed delivery recorded for `run`, or None."""
    delivery: Delivery | None = None
    started: dict | None = None
    gates: dict | None = None
    for event in events:
        payload = event.payload or {}
        if event.event_type == "delivery.started":
            started = payload if payload.get("task_id") == run.task_id else None
            gates = None
        elif event.event_type == "delivery.gates_passed" and started is not None:
            gates = payload
        elif event.event_type == "delivery.pr_opened" and started is not None and gates is not None:
            delivery = Delivery(
                run_id=str(run.id),
                task_id=run.task_id,
                branch=payload["branch"],
                base_sha=started.get("base_sha") or "",
                commit_sha=payload["commit_sha"],
                changed_paths=gates.get("changed_paths", []),
                pr_number=payload["pr_number"],
                pr_url=payload["pr_url"],
                tests_passed=gates.get("tests_passed", 0),
                evidence=[EvidenceRef(**ref) for ref in payload.get("evidence", [])],
            )
    return delivery


@router.get("/projects/{project_id}/traceability", response_model=TraceabilityResponse)
async def project_traceability(
    project_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> TraceabilityResponse:
    """Delivered pull requests for the project's runs, with their evidence."""
    try:
        get_project(session, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    runs = await SqlAlchemyArtifactRepository(session).list_artifacts(project_id, ArtifactKind.run)
    store = RunStore(session)
    deliveries = [
        d for run in runs if isinstance(run, Run)
        if (d := delivery_from_events(run, store.events_since(str(run.id)))) is not None
    ]
    return TraceabilityResponse(deliveries=deliveries)
