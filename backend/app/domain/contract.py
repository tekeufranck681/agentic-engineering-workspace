"""ENG-004 EngineeringContract model (discriminated union)."""

from typing import Annotated, ClassVar, Literal, Union

from pydantic import Field

from .base import Artifact, DomainModel
from .enums import ArtifactKind, ArtifactStatus


class ApiEndpoint(DomainModel):
    method: str
    path: str
    summary: str
    request_schema: dict | None = None
    response_schema: dict | None = None


class ApiContractContent(DomainModel):
    kind: Literal["api"] = "api"
    endpoints: list[ApiEndpoint] = Field(default_factory=list)


class DbColumn(DomainModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    references: str | None = None


class DbTable(DomainModel):
    name: str
    columns: list[DbColumn] = Field(default_factory=list)


class DbSchemaContractContent(DomainModel):
    kind: Literal["db_schema"] = "db_schema"
    tables: list[DbTable] = Field(default_factory=list)


class UmlContractContent(DomainModel):
    kind: Literal["uml"] = "uml"
    diagram_type: str
    source: str  # Mermaid text


EngineeringContractContent = Annotated[
    Union[ApiContractContent, DbSchemaContractContent, UmlContractContent],
    Field(discriminator="kind"),
]


class EngineeringContract(Artifact):
    """An engineering contract: API spec, DB schema, or UML diagram."""

    ARTIFACT_KIND: ClassVar[ArtifactKind] = ArtifactKind.contract

    content: EngineeringContractContent
    status: ArtifactStatus = ArtifactStatus.draft
