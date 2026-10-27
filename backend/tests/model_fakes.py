"""Scripted model provider shared by the gateway and capability runtime tests."""

import time
from collections.abc import Callable

from app.modules.model_gateway.provider import ProviderHealth, ProviderReply

PINNED = "nvidia/nemotron-test"


class ScriptedProvider:
    """Returns queued replies (or raises queued errors) and records each call."""

    name = "scripted"

    def __init__(
        self,
        *replies: str | Exception,
        delay: float = 0.0,
        answered_by: str | None = PINNED,
        routed_provider: str | None = "nvidia",
        tokens: tuple[int | None, int | None] = (10, 5),
        cost_usd: float | None = None,
    ) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.delay = delay
        self.on_call: Callable[[], None] | None = None
        self.answered_by = answered_by
        self.routed_provider = routed_provider
        self.tokens = tokens
        self.cost_usd = cost_usd

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, state="online", endpoint="scripted://")

    def complete(self, model, messages, *, max_tokens=None, temperature=None) -> ProviderReply:
        self.calls.append(
            {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        )
        if self.on_call is not None:
            self.on_call()
        if self.delay:
            time.sleep(self.delay)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ProviderReply(
            content=reply,
            answered_by=self.answered_by,
            attribution_source="runtime receipt" if self.answered_by else "not reported by the runtime",
            runtime_receipt_id="rcpt-1",
            routed_provider=self.routed_provider,
            prompt_tokens=self.tokens[0],
            completion_tokens=self.tokens[1],
            finish_reason="stop",
            latency_ms=7,
            cost_usd=self.cost_usd,
        )

    def close(self) -> None:
        pass
