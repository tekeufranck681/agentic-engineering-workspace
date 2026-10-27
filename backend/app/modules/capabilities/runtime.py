"""Capability runtime (ENG-028): validated, bounded, observable capability calls.

``invoke`` renders a contract's versioned prompt template from validated
inputs; ``run_prompt`` takes a caller-built prompt (the path behind
CapabilityPort, the LLMPort that M4's services use). Either way the runtime

* puts the contract's versioned instructions ahead of the gateway's JSON
  Schema instructions and validates the reply against the output schema;
* repairs malformed output at most ``max_repairs`` times, showing the model
  its previous reply and the validation errors;
* retries retryable provider failures (timeouts, 429, 5xx) at most
  ``max_retries`` times with linear backoff: an infrastructure retry, never an
  engineering correction (architecture §53);
* enforces the contract timeout and checks the CancellationToken around every
  model call;
* checks the invocation's budget and the caller's run budget before every
  model call and charges each call to them (ENG-043);
* for contracts that recall memory, adds the project's relevant H-MEM lessons
  to the prompt first, and fails closed when the engine cannot answer;
* records one CapabilityInvocationReceipt per invocation.

Nothing loops unbounded: at most 1 + max_repairs + max_retries model calls.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.modules.capabilities.budgets import BudgetLedger
from app.modules.capabilities.contract import CancellationToken, CapabilityContract, InvocationContext
from app.modules.capabilities.errors import (
    CapabilityCancelledError,
    CapabilityError,
    CapabilityInputError,
    CapabilityMemoryError,
    CapabilityOutputError,
    CapabilityTimeoutError,
)
from app.modules.capabilities.receipts import CapabilityInvocationReceipt, ModelCallRouting
from app.modules.capabilities.registry import CapabilityRegistry
from app.modules.memory.errors import AgentMemoryError
from app.modules.memory.models import MemoryRecallEvidence
from app.modules.memory.provider import AgentMemoryProvider
from app.modules.memory.recall import recall_into_prompt
from app.modules.model_gateway.errors import ModelGatewayError, StructuredOutputError
from app.modules.model_gateway.gateway import ModelGateway, summarize_validation_error
from app.modules.model_gateway.receipts import InMemoryReceiptSink, ModelCallReceipt, ReceiptSink

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

REPAIR_PROMPT = (
    "Your previous reply could not be used: {reason}\n\n"
    "Previous reply:\n{reply}\n\n"
    "Original request:\n{prompt}\n\n"
    "Reply again with only the corrected JSON object."
)
_MAX_REPLY_IN_REPAIR = 8000


@dataclass(frozen=True)
class CapabilityResult(Generic[T]):
    value: T
    receipt: CapabilityInvocationReceipt


@dataclass
class _Progress:
    calls: list[ModelCallReceipt] = field(default_factory=list)
    repairs: int = 0
    retries: int = 0
    ledgers: list[BudgetLedger] = field(default_factory=list)

    def note(self, receipt: ModelCallReceipt | None) -> None:
        if receipt is not None:
            self.calls.append(receipt)
            for ledger in self.ledgers:
                ledger.charge(receipt)


class CapabilityRuntime:
    """Invokes registered capabilities through the ModelGateway."""

    def __init__(
        self,
        gateway: ModelGateway,
        registry: CapabilityRegistry,
        sink: ReceiptSink | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        memory: AgentMemoryProvider | None = None,
        recall_top_n: int = 5,
        recall_threshold: float = 0.35,
    ) -> None:
        self._gateway = gateway
        self.registry = registry
        self.receipts = sink if sink is not None else InMemoryReceiptSink()
        self._sleep = sleep
        self._memory = memory
        self._recall_top_n = recall_top_n
        self._recall_threshold = recall_threshold

    def port(
        self, capability: str, context: InvocationContext | None = None, budget: BudgetLedger | None = None
    ) -> "CapabilityPort":
        """An LLMPort bound to one registered capability (and optionally a run's budget)."""
        self.registry.get(capability)  # unknown names fail here, not on first use
        return CapabilityPort(self, capability, context, budget)

    async def invoke(
        self,
        capability: str,
        inputs: Mapping[str, Any] | BaseModel,
        *,
        context: InvocationContext | None = None,
        cancel: CancellationToken | None = None,
        budget: BudgetLedger | None = None,
    ) -> CapabilityResult:
        """Render the contract's prompt template from ``inputs`` and run it.

        ``budget`` is the caller's run ledger, charged on top of the invocation's own.
        """
        contract = self.registry.get(capability)
        if contract.prompt_template is None or contract.output_schema is None:
            raise CapabilityInputError(
                f"{contract.name} declares no prompt template and output schema; use run_prompt",
                capability=contract.name,
            )
        prompt = _render(contract, inputs)
        return await self._run(contract, prompt, contract.output_schema, context, cancel, budget)

    async def run_prompt(
        self,
        capability: str,
        prompt: str,
        schema: type[T],
        *,
        context: InvocationContext | None = None,
        cancel: CancellationToken | None = None,
        budget: BudgetLedger | None = None,
    ) -> CapabilityResult[T]:
        """Run a caller-built prompt under the capability's contract."""
        return await self._run(self.registry.get(capability), prompt, schema, context, cancel, budget)

    # ---------------------------------------------------------------- internals

    async def _run(
        self,
        contract: CapabilityContract,
        prompt: str,
        schema: type[T],
        context: InvocationContext | None,
        cancel: CancellationToken | None,
        budget: BudgetLedger | None = None,
    ) -> CapabilityResult[T]:
        context = context or InvocationContext()
        progress = _Progress()
        if contract.budget is not None:
            progress.ledgers.append(BudgetLedger(contract.budget, scope=f"{contract.name} invocation"))
        if budget is not None:
            progress.ledgers.append(budget)
        memory: MemoryRecallEvidence | None = None
        invocation_id = str(uuid.uuid4())
        started_at, started = datetime.now(timezone.utc), time.monotonic()

        def finish(outcome: str, *, error_kind: str | None = None, value: BaseModel | None = None):
            receipt = CapabilityInvocationReceipt(
                invocation_id=invocation_id,
                capability=contract.name,
                capability_version=contract.version,
                outcome=outcome,
                error_kind=error_kind,
                project_id=context.project_id,
                run_id=context.run_id,
                step_id=context.step_id,
                input_refs=list(context.input_refs),
                input_sha256=_sha256(prompt),
                output_schema=schema.__name__,
                output_sha256=_sha256(value.model_dump_json()) if value is not None else None,
                model_calls=[call.call_id for call in progress.calls],
                answered_by=[call.answered_by for call in progress.calls if call.answered_by],
                attempts=len(progress.calls),
                repairs=progress.repairs,
                retries=progress.retries,
                duration_ms=int((time.monotonic() - started) * 1000),
                started_at=started_at,
                memory=memory,
                calls=[ModelCallRouting.of(call) for call in progress.calls],
                tokens=sum((call.prompt_tokens or 0) + (call.completion_tokens or 0) for call in progress.calls),
                cost_usd=_reported_cost(progress.calls),
                budgets=[ledger.usage() for ledger in progress.ledgers],
            )
            self._record(receipt)
            return receipt

        try:
            if contract.recalls_memory:
                prompt, memory = await self._recall(contract, prompt, context, invocation_id)
            value = await asyncio.wait_for(
                self._attempts(contract, prompt, schema, cancel, progress),
                timeout=contract.timeout_seconds,
            )
        except TimeoutError as exc:
            error = CapabilityTimeoutError(
                f"{contract.name} v{contract.version} did not finish within {contract.timeout_seconds:g} s",
                capability=contract.name,
                invocation_id=invocation_id,
            )
            finish("timeout", error_kind=error.kind)
            raise error from exc
        except CapabilityError as exc:
            exc.invocation_id = invocation_id
            finish("cancelled" if isinstance(exc, CapabilityCancelledError) else "failed", error_kind=exc.kind)
            raise
        except ModelGatewayError as exc:
            finish("failed", error_kind=exc.kind)
            raise
        return CapabilityResult(value=value, receipt=finish("ok", value=value))

    async def _attempts(
        self,
        contract: CapabilityContract,
        prompt: str,
        schema: type[T],
        cancel: CancellationToken | None,
        progress: _Progress,
    ) -> T:
        request = prompt
        while True:
            _raise_if_cancelled(cancel, contract)
            for ledger in progress.ledgers:
                ledger.check(contract.name)
            try:
                result = await self._gateway.structured_call(
                    request, schema, capability=contract.name, instructions=contract.instructions
                )
            except StructuredOutputError as exc:
                progress.note(exc.receipt)
                if progress.repairs >= contract.max_repairs:
                    raise CapabilityOutputError(
                        f"{contract.name} v{contract.version}: output still invalid after "
                        f"{progress.repairs} repair(s): {exc}",
                        capability=contract.name,
                    ) from exc
                progress.repairs += 1
                request = REPAIR_PROMPT.format(
                    reason=exc, reply=exc.reply_text[:_MAX_REPLY_IN_REPAIR], prompt=prompt
                )
                continue
            except ModelGatewayError as exc:
                progress.note(exc.receipt)
                if not exc.retryable or progress.retries >= contract.max_retries:
                    raise
                progress.retries += 1
                _raise_if_cancelled(cancel, contract)
                await self._sleep(contract.retry_backoff_seconds * progress.retries)
                continue
            progress.note(result.receipt)
            _raise_if_cancelled(cancel, contract)  # a cancelled invocation discards a late result
            return result.value

    async def _recall(
        self, contract: CapabilityContract, prompt: str, context: InvocationContext, invocation_id: str
    ) -> tuple[str, MemoryRecallEvidence]:
        """Add the project's relevant H-MEM lessons to the prompt; fail closed if the engine cannot answer."""
        if context.project_id is None:
            evidence = MemoryRecallEvidence(status="skipped", reason="no project in the invocation context")
        elif self._memory is None:
            raise CapabilityMemoryError(
                f"{contract.name} v{contract.version} recalls project memory, but no memory provider is configured",
                capability=contract.name,
            )
        else:
            try:
                prompt, evidence = await asyncio.to_thread(
                    recall_into_prompt,
                    self._memory,
                    context.project_id,
                    prompt,
                    query=context.memory_query,
                    top_n=self._recall_top_n,
                    threshold=self._recall_threshold,
                )
            except AgentMemoryError as exc:
                error = CapabilityMemoryError(
                    f"{contract.name} v{contract.version}: project memory (H-MEM) did not answer, "
                    f"so the capability does not run without it: {exc}",
                    capability=contract.name,
                )
                error.retryable = exc.retryable
                raise error from exc
        if evidence.status == "recalled":
            logger.info(
                "capability %s v%s invocation %s: H-MEM recalled %s for project %s into the prompt (%s)",
                contract.name,
                contract.version,
                invocation_id,
                ", ".join(f"{m.memory_id} relevance={m.relevance:.3f} from {m.source}" for m in evidence.memories),
                evidence.project_id,
                evidence.reason,
            )
        else:
            logger.info(
                "capability %s v%s invocation %s: no H-MEM lesson added (%s: %s)",
                contract.name,
                contract.version,
                invocation_id,
                evidence.status,
                evidence.reason,
            )
        return prompt, evidence

    def _record(self, receipt: CapabilityInvocationReceipt) -> None:
        self.receipts.record(receipt)
        logger.info(
            "capability %s v%s invocation %s outcome=%s%s attempts=%s repairs=%s retries=%s "
            "answered_by=%s memory=%s duration_ms=%s",
            receipt.capability,
            receipt.capability_version,
            receipt.invocation_id,
            receipt.outcome,
            f" error={receipt.error_kind}" if receipt.error_kind else "",
            receipt.attempts,
            receipt.repairs,
            receipt.retries,
            ",".join(receipt.answered_by) or None,
            _memory_summary(receipt.memory),
            receipt.duration_ms,
        )


class CapabilityPort:
    """LLMPort for services that build their own prompts: same bounds, repair and receipts."""

    def __init__(
        self,
        runtime: CapabilityRuntime,
        capability: str,
        context: InvocationContext | None = None,
        budget: BudgetLedger | None = None,
    ) -> None:
        self._runtime = runtime
        self.capability = capability
        self._context = context
        self._budget = budget

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        result = await self._runtime.run_prompt(
            self.capability, prompt, schema, context=self._context, budget=self._budget
        )
        return result.value


def _reported_cost(calls: list[ModelCallReceipt]) -> float | None:
    costs = [call.cost_usd for call in calls if call.cost_usd is not None]
    return round(sum(costs), 6) if costs else None


def _memory_summary(memory: MemoryRecallEvidence | None) -> str | None:
    if memory is None:
        return None
    ids = ",".join(m.memory_id for m in memory.memories)
    return f"{memory.status}:{ids}" if ids else memory.status


def _render(contract: CapabilityContract, inputs: Mapping[str, Any] | BaseModel) -> str:
    """The contract's prompt with validated inputs filled in."""
    if contract.input_schema is not None:
        try:
            model = (
                inputs
                if isinstance(inputs, contract.input_schema)
                else contract.input_schema.model_validate(
                    inputs.model_dump() if isinstance(inputs, BaseModel) else dict(inputs)
                )
            )
        except ValidationError as exc:
            raise CapabilityInputError(
                f"{contract.name} v{contract.version}: invalid inputs: {summarize_validation_error(exc)}",
                capability=contract.name,
            ) from exc
        values = model.model_dump()
    else:
        values = inputs.model_dump() if isinstance(inputs, BaseModel) else dict(inputs)
    try:
        return contract.prompt_template.format_map(values)
    except (KeyError, IndexError) as exc:
        raise CapabilityInputError(
            f"{contract.name} v{contract.version}: the prompt template needs input {exc}",
            capability=contract.name,
        ) from exc


def _raise_if_cancelled(cancel: CancellationToken | None, contract: CapabilityContract) -> None:
    if cancel is not None and cancel.cancelled:
        reason = f": {cancel.reason}" if cancel.reason else ""
        raise CapabilityCancelledError(f"{contract.name} cancelled{reason}", capability=contract.name)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
