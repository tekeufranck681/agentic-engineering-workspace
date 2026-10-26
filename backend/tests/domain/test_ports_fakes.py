"""Tests for ports and fakes."""

import pytest
from uuid import uuid4

from app.domain.ports import LLMPort, RepositoryPort
from app.domain.fakes import InMemoryRepository, FakeLLM
from app.domain.base import DomainModel
from app.domain.enums import ArtifactKind, ArtifactStatus
from app.domain.requirements import Requirement


class SampleModel(DomainModel):
    name: str
    value: int


@pytest.mark.asyncio
async def test_fake_llm_returns_registered_response():
    llm = FakeLLM(responses={"SampleModel": {"name": "x", "value": 42}})
    result = await llm.generate_structured("prompt", SampleModel)
    assert isinstance(result, SampleModel)
    assert result.name == "x"
    assert result.value == 42
    assert len(llm.calls) == 1
    assert llm.calls[0][0] == "prompt"
    assert llm.calls[0][1] == "SampleModel"


@pytest.mark.asyncio
async def test_fake_llm_missing_response_raises():
    llm = FakeLLM(responses={})
    with pytest.raises(KeyError):
        await llm.generate_structured("prompt", SampleModel)


@pytest.mark.asyncio
async def test_in_memory_next_id_increments_per_kind():
    repo = InMemoryRepository()
    pid = uuid4()
    id1 = await repo.next_id(pid, ArtifactKind.requirement)
    id2 = await repo.next_id(pid, ArtifactKind.requirement)
    id3 = await repo.next_id(pid, ArtifactKind.task)
    assert id1 == "REQ-001"
    assert id2 == "REQ-002"
    assert id3 == "TASK-001"


@pytest.mark.asyncio
async def test_in_memory_save_and_get_latest():
    repo = InMemoryRepository()
    pid = uuid4()
    req = Requirement(
        id="REQ-001",
        project_id=pid,
        title="T",
        description="D",
        type="functional",
        priority="must",
        status="draft",
    )
    await repo.save_artifact(req)
    fetched = await repo.get_artifact(pid, "REQ-001")
    assert fetched is not None
    assert fetched.title == "T"


@pytest.mark.asyncio
async def test_in_memory_get_nonexistent():
    repo = InMemoryRepository()
    pid = uuid4()
    result = await repo.get_artifact(pid, "REQ-999")
    assert result is None


@pytest.mark.asyncio
async def test_in_memory_list_by_kind_and_status():
    repo = InMemoryRepository()
    pid = uuid4()
    req1 = Requirement(
        id="REQ-001", project_id=pid, title="A", description="D",
        type="functional", priority="must", status="draft",
    )
    req2 = Requirement(
        id="REQ-002", project_id=pid, title="B", description="D",
        type="functional", priority="should", status="approved",
    )
    await repo.save_artifact(req1)
    await repo.save_artifact(req2)

    all_reqs = await repo.list_artifacts(pid, ArtifactKind.requirement)
    assert len(all_reqs) == 2

    drafts = await repo.list_artifacts(pid, ArtifactKind.requirement, status="draft")
    assert len(drafts) == 1
    assert drafts[0].title == "A"
