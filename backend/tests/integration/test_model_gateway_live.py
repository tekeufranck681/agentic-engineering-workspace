"""Live ModelGateway checks against the real Nightshift runtime (ENG-008).

Skipped unless NIGHTSHIFT_LIVE=1. Reads NIGHTSHIFT_* and MODEL_GATEWAY_* from
the environment or the repo-root .env, so run it on the backend host:

    NIGHTSHIFT_LIVE=1 python -m pytest tests/integration -q

A status probe and two small model calls. The requirements flow runs through
the capability runtime in test_capability_runtime_live.py.
"""

import os

import pytest
from pydantic import BaseModel

from app.modules.capabilities.registry import REQUIREMENTS_ANALYZE
from app.modules.model_gateway.api import build_model_gateway
from app.modules.model_gateway.receipts import ModelCallReceipt

pytestmark = pytest.mark.skipif(
    os.environ.get("NIGHTSHIFT_LIVE") != "1", reason="set NIGHTSHIFT_LIVE=1 to call the real Nightshift runtime"
)

DEMO_BRIEF = (
    "Add subscription billing. A subscription only becomes ACTIVE after payment "
    "confirmation; a failed or unconfirmed payment must never activate it."
)


class Classification(BaseModel):
    is_billing_related: bool
    reason: str


@pytest.fixture(scope="module")
def gateway():
    gateway = build_model_gateway()
    yield gateway
    gateway.close()


def assert_attributed(receipt: ModelCallReceipt) -> None:
    assert receipt.outcome == "ok"
    assert receipt.provider == "nightshift"
    assert receipt.answered_by and not receipt.answered_by.startswith("meterless/")
    assert receipt.runtime_receipt_id


async def test_health_lists_the_routing_lanes(gateway):
    health = await gateway.health()
    assert (health.provider, health.state) == ("nightshift", "online")
    assert gateway.lane_for(REQUIREMENTS_ANALYZE) in health.model_ids


async def test_generate_on_the_default_lane(gateway):
    result = await gateway.generate("Reply with exactly NIGHTSHIFT_OK and nothing else.")
    assert "NIGHTSHIFT_OK" in result.text.upper()
    assert_attributed(result.receipt)


async def test_generate_structured(gateway):
    verdict = await gateway.generate_structured(
        f"Is this request about billing?\n\n{DEMO_BRIEF}", Classification
    )
    assert verdict.is_billing_related is True
    assert_attributed(gateway.receipts.recent()[0])
