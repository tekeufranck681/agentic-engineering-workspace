# aew-demo-target

Demo repository for the Agentic Engineering Workspace (Open Agent Hackathon 2026).
The workspace's agent changes this repository in an isolated sandbox and
delivers its work as pull requests. It is throwaway: do not use it for anything else.

## Scenario: REQ-001, activate only after payment confirmation

A subscription becomes ACTIVE only when its payment is confirmed.

| AC | Rule | Test |
|---|---|---|
| AC-001 | A failed or unconfirmed payment does not activate the subscription | `tests/test_service.py::test_ac_001_unconfirmed_payment_does_not_activate` |
| AC-002 | A confirmed payment activates the subscription | `tests/test_service.py::test_ac_002_confirmed_payment_activates` |

**Known defect (deliberate):** `BillingService.activate` only refuses *failed*
payments, so a *pending* (unconfirmed) payment still activates the subscription.
AC-001 fails until the agent fixes `app/billing/service.py` (TASK-002).

## Run the tests

```
python -m pip install pytest
python -m pytest -q
```

Expected before the fix: 1 failed (AC-001, the pending case), everything else passes.
