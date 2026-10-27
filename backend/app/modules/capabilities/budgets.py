"""Capability budgets (ENG-043): ceilings on model calls, tokens, time and cost.

A ``Budget`` holds ceilings; a ``BudgetLedger`` counts usage against one.
Every invocation gets a ledger from its contract's budget, and an orchestrator
can pass one ledger to every invocation of a run, so the run stops once it has
spent its allowance, whichever capabilities spent it. The runtime checks the
ledgers before each model call (repairs and retries included) and charges each
call's receipt after it. A reached ceiling raises ``CapabilityBudgetError``:
not retryable, and the message says which ceiling and how much was used.

Tokens are the runtime's reported prompt and completion tokens; a successful
reply without them is estimated from characters (4 per token) and counted as
estimated. Cost is the runtime's reported ``actual_usd``; a reply without a
cost counts as unpriced, never as free.
"""

import math
import threading
import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from app.modules.capabilities.errors import CapabilityBudgetError
from app.modules.model_gateway.receipts import ModelCallReceipt

CHARS_PER_TOKEN = 4


class Budget(BaseModel):
    """Ceilings; None leaves a measure unbounded."""

    model_config = ConfigDict(frozen=True)

    max_model_calls: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    max_seconds: float | None = Field(default=None, gt=0)
    max_cost_usd: float | None = Field(default=None, gt=0)


# Per invocation unless a contract sets its own: roomy next to the 4,096-token
# completion budget per call and the 1 + repairs + retries calls an invocation
# may make. Time is already bounded by the contract timeout.
DEFAULT_INVOCATION_BUDGET = Budget(max_tokens=60_000)


class BudgetUsage(BaseModel):
    """What a ledger has spent, next to its ceilings."""

    scope: str
    budget: Budget
    model_calls: int = 0
    tokens: int = 0
    estimated_tokens: int = Field(default=0, description="Part of tokens estimated from characters")
    cost_usd: float = 0.0
    unpriced_calls: int = Field(default=0, description="Answered calls whose receipt carried no cost")
    seconds: float = 0.0


class BudgetLedger:
    """Thread-safe usage against one Budget; one per invocation, or shared by a run."""

    def __init__(self, budget: Budget, *, scope: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.budget = budget
        self.scope = scope
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self._usage = BudgetUsage(scope=scope, budget=budget)

    def check(self, capability: str) -> None:
        """Raise CapabilityBudgetError when a ceiling is already reached."""
        with self._lock:
            reached = self._reached()
        if reached is not None:
            measure, used, ceiling = reached
            raise CapabilityBudgetError(
                f"{self.scope}: {measure} budget spent ({used:g} of {ceiling:g}); "
                f"{capability} makes no further model call",
                capability=capability,
                measure=measure,
                scope=self.scope,
            )

    def charge(self, receipt: ModelCallReceipt) -> None:
        """Count one model call from its receipt, answered or failed."""
        with self._lock:
            usage = self._usage
            usage.model_calls += 1
            if receipt.prompt_tokens is not None or receipt.completion_tokens is not None:
                usage.tokens += (receipt.prompt_tokens or 0) + (receipt.completion_tokens or 0)
            elif receipt.outcome == "ok" or receipt.response_chars is not None:
                estimate = math.ceil((receipt.prompt_chars + (receipt.response_chars or 0)) / CHARS_PER_TOKEN)
                usage.tokens += estimate
                usage.estimated_tokens += estimate
            if receipt.cost_usd is not None:
                usage.cost_usd += receipt.cost_usd
            elif receipt.outcome == "ok" or receipt.response_chars is not None:
                usage.unpriced_calls += 1

    def usage(self) -> BudgetUsage:
        with self._lock:
            return self._usage.model_copy(update={"seconds": round(self._clock() - self._started, 3)})

    def _reached(self) -> tuple[str, float, float] | None:
        budget, usage = self.budget, self._usage
        if budget.max_model_calls is not None and usage.model_calls >= budget.max_model_calls:
            return "model call", usage.model_calls, budget.max_model_calls
        if budget.max_tokens is not None and usage.tokens >= budget.max_tokens:
            return "token", usage.tokens, budget.max_tokens
        if budget.max_cost_usd is not None and usage.cost_usd >= budget.max_cost_usd:
            return "cost (USD)", round(usage.cost_usd, 6), budget.max_cost_usd
        elapsed = self._clock() - self._started
        if budget.max_seconds is not None and elapsed >= budget.max_seconds:
            return "time (s)", round(elapsed, 1), budget.max_seconds
        return None
