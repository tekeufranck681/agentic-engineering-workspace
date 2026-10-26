"""Live capability runtime check against the real Nightshift runtime (ENG-028).

Skipped unless NIGHTSHIFT_LIVE=1. M4's real requirements service analyzes the
canonical demo brief through the requirements capability: versioned
instructions, bounded repair and retries, invocation receipt.

    NIGHTSHIFT_LIVE=1 python -m pytest tests/integration -q
"""

import os
import uuid

import pytest

from app.domain.fakes import InMemoryRepository
from app.modules.capabilities.contract import InvocationContext
from app.modules.capabilities.registry import REQUIREMENTS_ANALYZE, default_registry
from app.modules.capabilities.runtime import CapabilityRuntime
from app.modules.model_gateway.api import build_model_gateway
from app.modules.requirements.service import RequirementsService

pytestmark = pytest.mark.skipif(
    os.environ.get("NIGHTSHIFT_LIVE") != "1", reason="set NIGHTSHIFT_LIVE=1 to call the real Nightshift runtime"
)

DEMO_BRIEF = (
    "Add subscription billing. A subscription only becomes ACTIVE after payment "
    "confirmation; a failed or unconfirmed payment must never activate it."
)


async def test_requirements_analysis_through_the_capability_runtime():
    gateway = build_model_gateway()
    runtime = CapabilityRuntime(gateway, default_registry())
    port = runtime.port(REQUIREMENTS_ANALYZE, InvocationContext(project_id="demo", input_refs=["brief@v1"]))
    try:
        requirements_set, requirements = await RequirementsService(
            llm=port, repo=InMemoryRepository()
        ).analyze_project(uuid.uuid4(), DEMO_BRIEF)
    finally:
        gateway.close()

    assert requirements and requirements_set.members
    receipt = runtime.receipts.recent()[0]
    assert (receipt.capability, receipt.capability_version, receipt.outcome) == (REQUIREMENTS_ANALYZE, "1.0.0", "ok")
    assert receipt.answered_by and not any(model.startswith("meterless/") for model in receipt.answered_by)
    assert receipt.input_refs == ["brief@v1"] and receipt.output_sha256
