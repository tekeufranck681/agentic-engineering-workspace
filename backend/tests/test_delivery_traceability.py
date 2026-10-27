"""GET /projects/{id}/traceability rebuilds deliveries from persisted run events."""

import uuid

from app.domain.enums import RunStatus
from app.domain.ids import ReadableId
from app.domain.run import Run
from app.modules.persistence.models import Project
from app.modules.persistence.requirements_repository import SqlAlchemyArtifactRepository
from app.modules.persistence.run_store import RunStore


async def test_traceability_lists_only_completed_deliveries_for_the_project(client, session):
    project = Project(name="delivery-test", description=None)
    session.add(project)
    session.commit()
    repo, store = SqlAlchemyArtifactRepository(session), RunStore(session)
    for rid, task in (("RUN-001", "TASK-001"), ("RUN-002", "TASK-002")):
        run = Run(id=ReadableId(rid), project_id=project.id, task_id=task, status=RunStatus.succeeded)
        run.seal()
        await repo.save_artifact(run)

    store.append_event("RUN-001", "delivery.started", {"task_id": "TASK-001", "base_sha": "base1"})
    store.append_event("RUN-001", "delivery.gates_passed", {"tests_passed": 5, "changed_paths": ["app/x.py"],
                                                            "evidence": [{"kind": "diff", "id": "EV-1"}]})
    store.append_event("RUN-001", "delivery.pr_opened", {"pr_number": 9, "pr_url": "https://github.com/o/r/pull/9",
                                                         "branch": "agent/run-001", "commit_sha": "c1",
                                                         "evidence": [{"kind": "diff", "id": "EV-1"},
                                                                      {"kind": "pull_request", "id": "EV-2"}]})
    # RUN-002 stopped at the gates: no PR, so no delivery.
    store.append_event("RUN-002", "delivery.started", {"task_id": "TASK-002", "base_sha": "base2"})

    body = client.get(f"/projects/{project.id}/traceability").json()
    assert [d["run_id"] for d in body["deliveries"]] == ["RUN-001"]
    d = body["deliveries"][0]
    assert (d["pr_number"], d["tests_passed"], d["base_sha"], d["changed_paths"]) == (9, 5, "base1", ["app/x.py"])
    assert [e["kind"] for e in d["evidence"]] == ["diff", "pull_request"]

    assert client.get(f"/projects/{uuid.uuid4()}/traceability").status_code == 404
