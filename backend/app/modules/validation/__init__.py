"""Validation plan and AC-to-test traceability (ENG-039).

Before implementation, the platform decides what proves success (HG/v1.0/10
§15): every acceptance criterion of a locked requirements set gets test intents
at validation levels L0-L4, each with Given/When/Then and executable checks
(pytest node ids the sandbox can run). A human approves the plan; the approved
version is the evaluator's stable AC-to-test mapping (ENG-033). Gaps are shown,
never assumed covered, and a plan whose pinned inputs changed is stale.

* ``plan``: generation through the ``planning.plan_validation`` capability,
  validation of the model's output, approval;
* ``traceability``: the AC-to-test matrix for the evaluator and the UI;
* ``router``: the API.
"""
