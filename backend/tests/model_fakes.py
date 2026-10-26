"""Scripted model provider shared by the gateway and capability runtime tests."""

import time
from collections.abc import Callable

from app.modules.model_gateway.provider import ProviderHealth, ProviderReply

PINNED = "nvidia/nemotron-test"


class ScriptedProvider:
    """Returns queued replies (or raises queued errors) and records each call."""

    name = "scripted"

    def __init__(self, *replies: str | Exception, delay: float = 0.0) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.delay = delay
        self.on_call: Callable[[], None] | None = None

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
            answered_by=PINNED,
            attribution_source="runtime receipt",
            runtime_receipt_id="rcpt-1",
            routed_provider="nvidia",
            prompt_tokens=10,
            completion_tokens=5,
            finish_reason="stop",
            latency_ms=7,
        )

    def close(self) -> None:
        pass
