"""Tests for ArchitectureDoc, ArchitectureDecision, and EngineeringContract."""

from uuid import uuid4

from app.domain.architecture import ArchitectureDoc, Component
from app.domain.adr import ArchitectureDecision
from app.domain.contract import (
    EngineeringContract,
    ApiContractContent,
    DbSchemaContractContent,
    UmlContractContent,
)
from app.domain.enums import ArtifactStatus, ArtifactKind


def test_architecture_doc():
    arch = ArchitectureDoc(
        id="ARCH-001",
        project_id=uuid4(),
        summary="Microservice architecture",
        components=[
            Component(
                name="api-gateway",
                responsibility="route requests",
                depends_on=["auth-service"],
                requirement_ids=["REQ-001"],
            )
        ],
        decision_ids=["ADR-001"],
    )
    assert arch.summary == "Microservice architecture"
    assert len(arch.components) == 1
    assert arch.components[0].name == "api-gateway"
    assert arch.status == ArtifactStatus.draft


def test_adr():
    adr = ArchitectureDecision(
        id="ADR-001",
        project_id=uuid4(),
        title="Use PostgreSQL",
        context="Need relational storage",
        decision="Adopt PostgreSQL 16",
        alternatives=["MySQL", "MongoDB"],
        consequences=["ACID compliance", "operational overhead"],
    )
    assert adr.title == "Use PostgreSQL"
    assert len(adr.alternatives) == 2


def test_engineering_contract_api():
    content = ApiContractContent(
        endpoints=[
            {
                "method": "GET",
                "path": "/users",
                "summary": "List users",
                "response_schema": {"type": "object"},
            }
        ]
    )
    contract = EngineeringContract(
        id="CON-001",
        project_id=uuid4(),
        content=content,
    )
    assert contract.content.kind == "api"
    assert len(contract.content.endpoints) == 1
    assert contract.content.endpoints[0].method == "GET"


def test_engineering_contract_db_schema():
    content = DbSchemaContractContent(
        tables=[
            {
                "name": "users",
                "columns": [
                    {"name": "id", "type": "uuid", "nullable": False, "primary_key": True},
                    {"name": "email", "type": "varchar", "nullable": False},
                ],
            }
        ]
    )
    contract = EngineeringContract(
        id="CON-002",
        project_id=uuid4(),
        content=content,
    )
    assert contract.content.kind == "db_schema"
    assert contract.content.tables[0].name == "users"


def test_engineering_contract_uml():
    content = UmlContractContent(
        diagram_type="class",
        source="class User { ... }",
    )
    contract = EngineeringContract(
        id="CON-003",
        project_id=uuid4(),
        content=content,
    )
    assert contract.content.kind == "uml"
    assert contract.content.diagram_type == "class"
