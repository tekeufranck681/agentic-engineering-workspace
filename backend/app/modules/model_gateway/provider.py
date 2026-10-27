"""Provider abstraction behind the ModelGateway, and its Nightshift adapter.

Only this module knows which runtime serves the models. Nightshift is the
primary and, for now, only provider (v2.0 POWER requirement). Nothing falls
back to another provider silently: a provider failure becomes a typed
ModelGatewayError and the caller decides what to do.
"""

from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from app.modules.model_gateway.errors import (
    ModelAuthError,
    ModelConfigError,
    ModelGatewayError,
    ModelProviderError,
    ModelRateLimitedError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from app.modules.nightshift.client import ChatMessage, NightshiftClient
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import (
    NightshiftAuthError,
    NightshiftConfigError,
    NightshiftError,
    NightshiftProviderError,
    NightshiftRateLimitedError,
    NightshiftRequestError,
    NightshiftResponseError,
    NightshiftUnavailableError,
)


class ProviderMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ProviderReply(BaseModel):
    """One completion plus provider-neutral attribution for its receipt."""

    content: str
    answered_by: str | None
    attribution_source: str
    runtime_receipt_id: str | None = None
    runtime_decision_id: str | None = None
    routed_provider: str | None = None
    from_cache: bool | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    latency_ms: int = Field(ge=0)
    cost_usd: float | None = None
    """What the runtime says the call cost, when its receipt carries a cost."""


class ProviderHealth(BaseModel):
    """Provider status from its model listing, for health endpoints (ENG-042)."""

    provider: str
    state: Literal["online", "unauthorized", "offline"]
    endpoint: str
    model_ids: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    detail: str = ""


class ModelProvider(Protocol):
    """What the gateway needs from a model runtime. Calls are blocking."""

    name: str

    def health(self) -> ProviderHealth: ...

    def complete(
        self,
        model: str,
        messages: list[ProviderMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ProviderReply: ...

    def close(self) -> None: ...


_TRANSLATIONS: tuple[tuple[type[NightshiftError], type[ModelGatewayError]], ...] = (
    (NightshiftConfigError, ModelConfigError),
    (NightshiftAuthError, ModelAuthError),
    (NightshiftRateLimitedError, ModelRateLimitedError),
    (NightshiftProviderError, ModelProviderError),
    (NightshiftRequestError, ModelRequestError),
    (NightshiftResponseError, ModelResponseError),
    (NightshiftUnavailableError, ModelUnavailableError),
)


def translate_nightshift_error(exc: NightshiftError) -> ModelGatewayError:
    """The gateway error for a Nightshift failure; its message is already redacted."""
    target = next(
        (gateway_error for source, gateway_error in _TRANSLATIONS if isinstance(exc, source)),
        ModelProviderError,
    )
    return target(
        f"nightshift: {exc}",
        retryable=exc.retryable,
        code=exc.code,
        status_code=exc.status_code,
        detail=exc.detail,
    )


class NightshiftProvider:
    """ModelProvider backed by the Meterless Runtime that Nightshift serves."""

    name = "nightshift"

    def __init__(self, client: NightshiftClient) -> None:
        self._client = client

    @classmethod
    def from_settings(
        cls, settings: NightshiftSettings, transport: httpx.BaseTransport | None = None
    ) -> "NightshiftProvider":
        try:
            return cls(NightshiftClient(settings, transport=transport))
        except NightshiftError as exc:
            raise translate_nightshift_error(exc) from exc

    def health(self) -> ProviderHealth:
        """Status per the provider guide: GET /v1/models, never /healthz."""
        probe = self._client.probe()
        return ProviderHealth(
            provider=self.name,
            state=probe.state.value,
            endpoint=probe.endpoint,
            model_ids=probe.model_ids,
            latency_ms=probe.latency_ms,
            detail=probe.detail,
        )

    def complete(
        self,
        model: str,
        messages: list[ProviderMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ProviderReply:
        try:
            result = self._client.chat(
                model,
                [ChatMessage(role=message.role, content=message.content) for message in messages],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except NightshiftError as exc:
            raise translate_nightshift_error(exc) from exc

        evidence = result.evidence
        answered_by, source = evidence.attribution()
        receipt = evidence.receipt
        usage = evidence.usage
        return ProviderReply(
            content=result.content,
            answered_by=answered_by,
            attribution_source=source,
            runtime_receipt_id=receipt.receipt_id if receipt else None,
            runtime_decision_id=receipt.decision_id if receipt else None,
            routed_provider=receipt.winning_route_provider if receipt else None,
            from_cache=receipt.from_cache if receipt else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            finish_reason=evidence.finish_reason,
            latency_ms=evidence.latency_ms,
            cost_usd=receipt.cost_usd if receipt else None,
        )

    def close(self) -> None:
        self._client.close()
