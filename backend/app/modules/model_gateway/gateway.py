"""ModelGateway (ENG-008): the single entry point for model calls.

Capabilities call ``generate`` for text or ``generate_structured`` for a
pydantic model and name their capability; configuration maps the capability
to a Nightshift lane or a pinned model id. ``for_capability`` binds the gateway
to one capability and is the LLMPort that M4's services receive. Every call
records a ModelCallReceipt, failures included. Provider calls are blocking
HTTP, so they run in a worker thread to keep the event loop free.

One call per request: versioned prompts, bounded output repair and retries
live in the capability runtime (``app.modules.capabilities``, ENG-028), which
capabilities should use; budgets come with ENG-043. A failure surfaces as a
typed ModelGatewayError; nothing falls back to another provider silently.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.errors import ModelGatewayError, StructuredOutputError
from app.modules.model_gateway.provider import (
    ModelProvider,
    ProviderHealth,
    ProviderMessage,
    ProviderReply,
)
from app.modules.model_gateway.receipts import InMemoryReceiptSink, ModelCallReceipt, ReceiptSink

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

STRUCTURED_INSTRUCTIONS = (
    "Answer with one JSON object and nothing else: no prose and no markdown fences. "
    "It must validate against this JSON Schema:\n{schema}"
)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S | re.I)
_MAX_ERROR_DETAILS = 5


class GenerationResult(BaseModel):
    text: str
    receipt: ModelCallReceipt


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    value: T
    receipt: ModelCallReceipt


class ModelGateway:
    """Routes capability calls to the provider and records a receipt for each."""

    def __init__(
        self,
        provider: ModelProvider,
        settings: ModelGatewaySettings,
        sink: ReceiptSink | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self.receipts = sink if sink is not None else InMemoryReceiptSink()

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def lane_for(self, capability: str | None) -> str:
        return self._settings.lane_for(capability)

    def for_capability(self, capability: str) -> "CapabilityModel":
        return CapabilityModel(self, capability)

    def close(self) -> None:
        self._provider.close()

    async def health(self) -> ProviderHealth:
        """The provider's status and advertised model ids (no model call)."""
        return await asyncio.to_thread(self._provider.health)

    async def generate(
        self,
        prompt: str,
        *,
        capability: str | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        """Plain-text completion."""
        reply, receipt = await self._call(
            _messages(prompt, system), capability=capability, max_tokens=max_tokens
        )
        self._record(receipt)
        return GenerationResult(text=reply.content, receipt=receipt)

    async def generate_structured(
        self, prompt: str, schema: type[T], *, capability: str | None = None
    ) -> T:
        """Completion parsed and validated into ``schema`` (M4's LLMPort contract)."""
        return (await self.structured_call(prompt, schema, capability=capability)).value

    async def structured_call(
        self,
        prompt: str,
        schema: type[T],
        *,
        capability: str | None = None,
        instructions: str | None = None,
    ) -> "StructuredResult[T]":
        """``generate_structured`` that also returns the call's receipt.

        ``instructions`` (a capability's versioned system prompt) precede the
        JSON Schema instructions. A raised ModelGatewayError carries the failed
        call's receipt in ``error.receipt``.
        """
        system = STRUCTURED_INSTRUCTIONS.format(
            schema=json.dumps(schema.model_json_schema(), separators=(",", ":"))
        )
        if instructions:
            system = f"{instructions}\n\n{system}"
        reply, receipt = await self._call(
            _messages(prompt, system), capability=capability, schema_name=schema.__name__
        )
        try:
            data = extract_json(reply.content)
        except ValueError as exc:
            raise self._structured_failure(receipt, schema, f"reply is not JSON: {exc}", reply) from exc
        try:
            value = schema.model_validate(data)
        except ValidationError as exc:
            raise self._structured_failure(receipt, schema, summarize_validation_error(exc), reply) from exc
        receipt = receipt.model_copy(update={"structured_valid": True})
        self._record(receipt)
        return StructuredResult(value=value, receipt=receipt)

    # ---------------------------------------------------------------- internals

    async def _call(
        self,
        messages: list[ProviderMessage],
        *,
        capability: str | None,
        max_tokens: int | None = None,
        schema_name: str | None = None,
    ) -> tuple[ProviderReply, ModelCallReceipt]:
        lane = self.lane_for(capability)
        digest, prompt_chars = _digest(messages)
        common = {
            "call_id": str(uuid.uuid4()),
            "capability": capability,
            "provider": self._provider.name,
            "requested_model": lane,
            "prompt_sha256": digest,
            "prompt_chars": prompt_chars,
            "structured_schema": schema_name,
            "started_at": datetime.now(timezone.utc),
        }
        started = time.monotonic()
        try:
            reply = await asyncio.to_thread(
                self._provider.complete,
                lane,
                messages,
                max_tokens=max_tokens or self._settings.max_tokens,
                temperature=self._settings.temperature,
            )
        except ModelGatewayError as exc:
            exc.receipt = ModelCallReceipt(
                **common,
                outcome="error",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_kind=exc.kind,
                error_code=exc.code,
                retryable=exc.retryable,
            )
            self._record(exc.receipt)
            raise
        receipt = ModelCallReceipt(
            **common,
            outcome="ok",
            answered_by=reply.answered_by,
            attribution_source=reply.attribution_source,
            runtime_receipt_id=reply.runtime_receipt_id,
            runtime_decision_id=reply.runtime_decision_id,
            routed_provider=reply.routed_provider,
            from_cache=reply.from_cache,
            response_chars=len(reply.content),
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            finish_reason=reply.finish_reason,
            latency_ms=reply.latency_ms,
        )
        return reply, receipt

    def _structured_failure(
        self,
        receipt: ModelCallReceipt,
        schema: type[BaseModel],
        reason: str,
        reply: ProviderReply,
    ) -> StructuredOutputError:
        error = StructuredOutputError(
            f"reply from {receipt.answered_by or 'the model'} is not a valid {schema.__name__}: {reason}",
            reply_text=reply.content,
        )
        error.receipt = receipt.model_copy(
            update={
                "outcome": "error",
                "structured_valid": False,
                "error_kind": error.kind,
                "retryable": error.retryable,
            }
        )
        self._record(error.receipt)
        return error

    def _record(self, receipt: ModelCallReceipt) -> None:
        self.receipts.record(receipt)
        logger.info(
            "model call %s capability=%s requested=%s answered_by=%s (%s) receipt=%s%s "
            "outcome=%s%s latency_ms=%s tokens=%s/%s",
            receipt.call_id,
            receipt.capability,
            receipt.requested_model,
            receipt.answered_by,
            receipt.attribution_source,
            receipt.runtime_receipt_id,
            " from_cache" if receipt.from_cache else "",
            receipt.outcome,
            f" error={receipt.error_kind}" if receipt.error_kind else "",
            receipt.latency_ms,
            receipt.prompt_tokens,
            receipt.completion_tokens,
        )


class CapabilityModel:
    """The gateway bound to one capability; satisfies M4's LLMPort."""

    def __init__(self, gateway: ModelGateway, capability: str) -> None:
        self._gateway = gateway
        self.capability = capability

    async def generate(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> GenerationResult:
        return await self._gateway.generate(
            prompt, capability=self.capability, system=system, max_tokens=max_tokens
        )

    async def generate_structured(self, prompt: str, schema: type[T]) -> T:
        return await self._gateway.generate_structured(prompt, schema, capability=self.capability)


def extract_json(text: str) -> object:
    """The JSON value in a model reply, tolerating think blocks, fences and stray prose."""
    cleaned = _THINK_BLOCK.sub("", text).strip()
    fenced = _JSON_FENCE.search(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= start < end:
            return json.loads(cleaned[start : end + 1])
        raise


def _messages(prompt: str, system: str | None) -> list[ProviderMessage]:
    messages = [ProviderMessage(role="system", content=system)] if system else []
    messages.append(ProviderMessage(role="user", content=prompt))
    return messages


def _digest(messages: list[ProviderMessage]) -> tuple[str, int]:
    """SHA-256 and character count of the prompt, without keeping its text."""
    canonical = json.dumps(
        [message.model_dump() for message in messages], sort_keys=True, separators=(",", ":")
    )
    return (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        sum(len(message.content) for message in messages),
    )


def summarize_validation_error(exc: ValidationError) -> str:
    """Field paths and messages only: never the offending input values."""
    errors = exc.errors()
    parts = [
        f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
        for error in errors[:_MAX_ERROR_DETAILS]
    ]
    if len(errors) > _MAX_ERROR_DETAILS:
        parts.append(f"+{len(errors) - _MAX_ERROR_DETAILS} more")
    return "; ".join(parts)
