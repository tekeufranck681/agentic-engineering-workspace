"""End-to-end engine feature (ENG-048): H-MEM changes a later architecture design.

A controlled pair on the product API. Two projects get the same locked
requirements; only one holds the verified AC-014-02 lesson an earlier run
learned. Both call POST /architecture/generate. The requirements say a
subscription activates after payment, but not what an unconfirmed or failed
payment does: that is what the lesson adds.

Asserted is the attribution chain: the engine's recall is the only difference
in what the model is asked (the lesson project's design prompt is the other
one plus the labelled H-MEM block), the receipts say recalled versus nothing
relevant, with memory id, score and source, and the engine's ledger records
the read. With NIGHTSHIFT_LIVE=1 Nightshift writes both designs (pin the
capability with MODEL_GATEWAY_LANES so both come from one model) and the test
prints them side by side for the evidence; a live model varies, so what each
design says is reported, not asserted. Without it a scripted model gives both
the same canned answer.

Phase ``feature`` of tests/integration/run_meterless_engine.sh
(HMEM_LIVE=1, HMEM_PHASE=feature).
"""

import json
import os
import re
import uuid

import pytest

from app.modules.capabilities import api as capabilities_api
from app.modules.memory.recall import RECALL_HEADER
from app.modules.requirements.service import LLMRequirementSpec, LLMRequirementsAnalysis
from tests.engine_fixtures import LESSON, LIVE_MODEL, add_project, client_for, engine_runtime, seed_locked_requirements

pytestmark = pytest.mark.skipif(
    os.environ.get("HMEM_LIVE") != "1" or os.environ.get("HMEM_PHASE") != "feature",
    reason="phase feature of run_meterless_engine.sh (HMEM_LIVE=1, HMEM_PHASE=feature)",
)

REQUIREMENTS = LLMRequirementsAnalysis(
    summary="Paid monthly subscriptions",
    requirements=[
        LLMRequirementSpec(
            title="Activate a subscription after payment",
            description="A customer buys a monthly plan; the subscription is activated after the payment.",
            type="functional",
            priority="must",
        ),
        LLMRequirementSpec(
            title="Subscription status",
            description="Customers see whether their subscription is pending, active or cancelled.",
            type="functional",
            priority="should",
        ),
    ],
)
SCRIPTED_DESIGN = {
    "summary": "Subscription billing",
    "components": [
        {
            "name": "BillingService",
            "responsibility": "Creates subscriptions and activates them after payment",
            "depends_on": ["PaymentProvider"],
            "requirement_ids": ["REQ-001", "REQ-002"],
        }
    ],
    "decision_summaries": [],
}
# What the lesson adds and the requirements do not say, looked for in each design.
LESSON_SIGNALS = {
    "activation waits for payment confirmation": r"confirm",
    "failed or declined payments handled": r"fail|declin",
    "provider callback or webhook": r"webhook|callback",
}


async def test_the_lesson_is_the_only_difference_and_reaches_the_design(session, monkeypatch):
    with_lesson = add_project(session, str(uuid.uuid4()), "engine-feature-with-lesson")
    without = add_project(session, str(uuid.uuid4()), "engine-feature-without-lesson")
    sets = {project: await seed_locked_requirements(session, project, REQUIREMENTS) for project in (without, with_lesson)}
    runtime, provider, gateway = engine_runtime(json.dumps(SCRIPTED_DESIGN), json.dumps(SCRIPTED_DESIGN))
    monkeypatch.setattr(capabilities_api, "get_capability_runtime", lambda: runtime)

    designs, first_call = {}, {}
    with client_for(session) as client:
        recorded = client.post(f"/projects/{with_lesson}/memory/lessons", json=LESSON)
        assert recorded.status_code == 201, recorded.text
        lesson = recorded.json()
        for project in (without, with_lesson):
            first_call[project] = len(provider.calls)
            response = client.post(
                "/architecture/generate", json={"project_id": project, "requirements_set_id": sets[project]}
            )
            assert response.status_code == 200, response.text
            designs[project] = response.json()
        history = client.get(f"/projects/{with_lesson}/memory/{lesson['id']}/history").json()["entries"]

    # The model was asked the same thing twice, except for the engine's block.
    asked = {project: provider.calls[first_call[project]]["messages"][1].content for project in designs}
    assert asked[with_lesson].startswith(asked[without])
    added = asked[with_lesson][len(asked[without]) :]
    assert added.startswith(f"\n\n{RECALL_HEADER}\n[MEMORY CONTEXT]")
    assert lesson["content"] in added and f"<{lesson['id']}>" in added

    # Receipts and the engine's ledger say when and why.
    receipts = {r.project_id: r for r in runtime.receipts.recent() if r.output_schema == "LLMArchitectureAnalysis"}
    assert (receipts[without].memory.status, receipts[without].memory.memories) == ("none_relevant", [])
    recall = receipts[with_lesson].memory
    assert recall.status == "recalled" and [m.memory_id for m in recall.memories] == [lesson["id"]]
    assert recall.memories[0].relevance >= recall.threshold and recall.memories[0].source == "run:RUN-0001"
    actions = [entry["action"] for entry in history]
    assert actions[0] == "create" and "read" in actions

    print("MODEL", "Nightshift (live)" if LIVE_MODEL else "scripted")
    print("LESSON", json.dumps({"id": lesson["id"], "content": lesson["content"], "source": lesson["source"]}))
    for label, project in (("WITHOUT", without), ("WITH", with_lesson)):
        design = designs[project]
        text = json.dumps(design)
        print(
            f"DESIGN_{label}",
            json.dumps(
                {
                    "project_id": project,
                    "summary": design["architecture"]["summary"],
                    "components": [
                        f"{c['name']}: {c['responsibility']}" for c in design["architecture"]["components"]
                    ],
                    "decisions": [f"{d['title']}: {d['decision']}" for d in design["decisions"]],
                    "signals": {name: bool(re.search(rx, text, re.I)) for name, rx in LESSON_SIGNALS.items()},
                }
            ),
        )
        print(f"RECEIPT_{label}", receipts[project].model_dump_json())
    print("ADDED_TO_PROMPT", json.dumps(added))
    print("LEDGER", json.dumps(actions))
    print(
        "MODEL_CALLS",
        json.dumps(
            [
                {
                    "capability": r.capability,
                    "requested": r.requested_model,
                    "answered_by": r.answered_by,
                    "attribution": r.attribution_source,
                    "from_cache": r.from_cache,
                    "runtime_receipt": r.runtime_receipt_id,
                    "tokens": [r.prompt_tokens, r.completion_tokens],
                    "latency_ms": r.latency_ms,
                    "schema": r.structured_schema,
                    "valid": r.structured_valid,
                }
                for r in reversed(gateway.receipts.recent())
            ]
        ),
    )
