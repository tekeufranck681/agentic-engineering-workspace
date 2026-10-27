"""SQLAlchemy adapter of the domain ``RepositoryPort`` (ENG-014/019).

M2's implementation of the port declared in ``app/domain/ports.py``: M4's
requirements service (and later other modules) program against the port; this
adapter is the only place that knows rows exist.

* async port methods wrap the sync ``sqlalchemy.orm.Session`` we already use
  everywhere (SQLite in tests, PostgreSQL in the team environments) — the MVP
  does not need a second, async database stack for this;
* every artifact version is an append-only row, mirroring the
  ``InMemoryRepository`` semantics the domain tests pin down;
* serialization is field-exact: Pydantic ``model_dump(mode="json")`` on the
  way in, ``model_validate`` on the way out — "every field has a column" is
  enforced by the round-trip tests, not by optimism.
"""

import uuid
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.base import Artifact
from app.domain.enums import ArtifactKind, ArtifactStatus
from app.domain.ids import ReadableId, format_id, parse_id
from app.modules.persistence.requirements_models import (
    ROW_CLASS_BY_KIND,
    ArtifactCounterRow,
    AcceptanceCriterionRow,
    RequirementRow,
    RequirementsSetRow,
    UserStoryRow,
)
from app.modules.persistence.architecture_models import (
    ARCH_ROW_CLASS_BY_KIND,
    AdrRow,
    ArchitectureRow,
    EngineeringContractRow,
    TaskRow,
)
from app.modules.persistence.run_models import RunRow
from app.modules.persistence.validation_models import VALIDATION_ROW_CLASS_BY_KIND, ValidationPlanRow

ROW_CLASS_BY_KIND["run"] = RunRow
ROW_CLASS_BY_KIND.update(ARCH_ROW_CLASS_BY_KIND)  # 0005: arch, ADR, contract, task
ROW_CLASS_BY_KIND.update(VALIDATION_ROW_CLASS_BY_KIND)  # 0006: validation plans (ENG-039)


class SqlAlchemyArtifactRepository:
    """RepositoryPort implementation backed by the requirements tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ ports

    async def next_id(self, project_id: uuid.UUID, kind: ArtifactKind) -> ReadableId:
        """Allocate the next readable ID for `kind` within `project_id`."""
        counter = self._session.get(
            ArtifactCounterRow, (project_id, kind.value)
        )
        if counter is None:
            counter = ArtifactCounterRow(
                project_id=project_id, kind=kind.value, current=0
            )
            self._session.add(counter)
        counter.current += 1
        self._session.commit()
        return ReadableId(format_id(kind.id_prefix, counter.current))

    async def save_artifact(self, artifact: Artifact) -> Artifact:
        """Persist `artifact` as one append-only row; return it unchanged."""
        row_class = ROW_CLASS_BY_KIND[artifact.ARTIFACT_KIND.value]
        dumped = artifact.model_dump(mode="json")
        row = row_class(
            id=str(artifact.id),
            project_id=artifact.project_id,
            version=artifact.version,
            schema_version=artifact.schema_version,
            status=artifact.status,
            created_at=artifact.created_at,
            content_hash=artifact.content_hash,
            trace=dumped["trace"],
            derived_from=dumped["derived_from"],
            **{
                key: dumped[key]
                for key in dumped
                if key
                not in {
                    "id",
                    "project_id",
                    "version",
                    "schema_version",
                    "status",
                    "created_at",
                    "content_hash",
                    "trace",
                    "derived_from",
                }
            },
        )
        self._session.add(row)
        self._session.commit()
        return artifact

    async def get_artifact(
        self, project_id: uuid.UUID, id: ReadableId, version: int | None = None
    ) -> Artifact | None:
        """Fetch an artifact by ID. If version is None, return the latest."""
        row = self._select_row(project_id, str(id), version)
        return self._to_domain(row) if row is not None else None

    async def list_artifacts(
        self,
        project_id: uuid.UUID,
        kind: ArtifactKind,
        status: ArtifactStatus | str | None = None,
    ) -> list[Artifact]:
        """List latest-version artifacts of `kind`, optionally filtered by status."""
        row_class = ROW_CLASS_BY_KIND[kind.value]
        statement = select(row_class).where(row_class.project_id == project_id)
        if status is not None:
            statement = statement.where(row_class.status == status)
        rows = list(self._session.scalars(statement).all())

        latest_by_id: dict[str, int] = {}
        for row in rows:
            if row.version > latest_by_id.get(row.id, 0):
                latest_by_id[row.id] = row.version
        return [
            self._to_domain(row)
            for row in rows
            if row.version == latest_by_id[row.id]
        ]

    # ---------------------------------------------------------------- helpers

    def _select_row(self, project_id: uuid.UUID, id: str, version: int | None):
        row_class = self._row_class_for_id(id)
        statement = select(row_class).where(
            row_class.project_id == project_id, row_class.id == id
        )
        if version is None:
            statement = statement.order_by(row_class.version.desc()).limit(1)
        else:
            statement = statement.where(row_class.version == version)
        return self._session.scalars(statement).first()

    @staticmethod
    def _row_class_for_id(id: str):
        """Map a readable id ("REQ-001") to its row class via the kind prefix."""
        row_class_by_prefix = {
            "REQ": RequirementRow,
            "US": UserStoryRow,
            "AC": AcceptanceCriterionRow,
            "RSET": RequirementsSetRow,
            "RUN": RunRow,
            "ARCH": ArchitectureRow,
            "ADR": AdrRow,
            "CON": EngineeringContractRow,
            "TASK": TaskRow,
            "VP": ValidationPlanRow,
        }
        prefix, _ = parse_id(id)
        try:
            return row_class_by_prefix[prefix]
        except KeyError:
            raise ValueError(f"unknown readable id prefix in {id!r}") from None

    @staticmethod
    def _to_domain(row) -> Artifact:
        """Rebuild the ENG-004 Pydantic artifact from its row (lossless)."""
        from app.domain.acceptance_criterion import AcceptanceCriterion
        from app.domain.adr import ArchitectureDecision
        from app.domain.architecture import ArchitectureDoc
        from app.domain.contract import EngineeringContract
        from app.domain.requirements import Requirement
        from app.domain.requirements_set import RequirementsSet
        from app.domain.run import Run
        from app.domain.task import Task
        from app.domain.user_story import UserStory
        from app.domain.validation_plan import ValidationPlan

        domain_class_by_row: dict[type, type[Artifact]] = {
            RequirementRow: Requirement,
            UserStoryRow: UserStory,
            AcceptanceCriterionRow: AcceptanceCriterion,
            RequirementsSetRow: RequirementsSet,
            RunRow: Run,
            ArchitectureRow: ArchitectureDoc,
            AdrRow: ArchitectureDecision,
            EngineeringContractRow: EngineeringContract,
            TaskRow: Task,
            ValidationPlanRow: ValidationPlan,
        }
        domain_class = domain_class_by_row[type(row)]
        payload = {
            key: getattr(row, key)
            for key in domain_class.model_fields
            if hasattr(row, key)
        }
        # SQLite stores DateTime(tz=True) without the offset; PostgreSQL keeps
        # it. Re-attach UTC so rows round-trip identically on both.
        created_at = payload.get("created_at")
        if created_at is not None and created_at.tzinfo is None:
            payload["created_at"] = created_at.replace(tzinfo=timezone.utc)
        return domain_class.model_validate(payload)
