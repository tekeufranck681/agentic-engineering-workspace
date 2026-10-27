"""ORM model for validation plans (0006, ENG-039).

Same per-kind table rule as 0002/0005: shared Artifact columns via
``_ArtifactColumnsMixin``, append-only versions (approval lands as a new
version), lowercase enum storage, JSON for the pinned refs and the test cases.
"""

from sqlalchemy import Index, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.enums import ArtifactStatus
from app.modules.persistence.requirements_models import _ArtifactColumnsMixin, _enum_column


class ValidationPlanRow(Base, _ArtifactColumnsMixin):
    """Row storage for app.domain.validation_plan.ValidationPlan."""

    __tablename__ = "validation_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "id", "version", name="uq_validation_plans_piv"),
        Index("ix_validation_plans_project_status", "project_id", "status"),
    )

    status: Mapped[ArtifactStatus] = mapped_column(
        _enum_column(ArtifactStatus), nullable=False, default=ArtifactStatus.draft
    )
    requirements_set: Mapped[dict] = mapped_column(JSON, nullable=False)
    requirement_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ac_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contract_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_levels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


VALIDATION_ROW_CLASS_BY_KIND = {"validation_plan": ValidationPlanRow}
