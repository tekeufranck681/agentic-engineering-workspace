"""Minimal, faithful client for the Meterless Runtime served by Nightshift.

Request mechanics follow the official Meterless provider guide
(``docs/agent-ready/add-meterless-provider.md`` in github.com/Meterless/Meterless):

* every request carries ``Authorization: Bearer <token>`` and
  ``meterless-app: <stable lowercase id>``; chat requests also carry
  ``meterless-scope: user``;
* ``GET {base}/models`` decides runtime status: 401/403 is unauthorized,
  200 listing ``meterless/*`` ids is online, anything else is offline
  (``/healthz`` only proves the process is up, so it is never used);
* ``POST {base}/chat/completions`` is OpenAI-compatible. ``meterless/auto``,
  ``meterless/fast`` and the other ``meterless/*`` ids are routing modes,
  not model names.

The client never logs or stores the token, maps failures to typed errors so
upper layers can tell refusal, overload, provider failure and outage apart,
and returns a redacted evidence record with every result.
"""

import time
import uuid
from typing import Literal

import httpx
from pydantic import BaseModel

from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import (
    NightshiftAuthError,
    NightshiftProviderError,
    NightshiftRateLimitedError,
    NightshiftRequestError,
    NightshiftResponseError,
    NightshiftUnavailableError,
)
from app.modules.nightshift.evidence import (
    ROUTING_MODE_PREFIX,
    ChatCallEvidence,
    ProbeEvidence,
    RuntimeReceipt,
    RuntimeState,
    TokenUsage,
    prompt_digest,
)

MODELS_PATH = "/models"
CHAT_PATH = "/chat/completions"
MAX_ERROR_TEXT = 200


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatResult(BaseModel):
    """The assistant's reply plus its evidence record."""

    content: str
    evidence: ChatCallEvidence


class NightshiftClient:
    """Synchronous client for the OpenAI-compatible Meterless Runtime API."""

    def __init__(
        self,
        settings: NightshiftSettings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings.require_credentials()
        self._settings = settings
        self._base = settings.base_url
        self._http = httpx.Client(
            base_url=self._base,
            timeout=httpx.Timeout(
                settings.timeout_seconds, connect=settings.connect_timeout_seconds
            ),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "NightshiftClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ HTTP

    def _headers(self, *, chat: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._settings.bearer_token()}",
            "meterless-app": self._settings.app_id,
        }
        if chat:
            headers["meterless-scope"] = "user"
        return headers

    def _send(
        self, method: str, path: str, *, chat: bool, json_body: dict | None = None
    ) -> tuple[httpx.Response, int]:
        """One authenticated request. Returns (response, latency in ms)."""
        started = time.monotonic()
        try:
            response = self._http.request(
                method, path, headers=self._headers(chat=chat), json=json_body
            )
        except httpx.TimeoutException as exc:
            raise NightshiftUnavailableError(
                f"nightshift did not answer at {self._base} within the timeout "
                f"(connect {self._settings.connect_timeout_seconds}s, "
                f"read {self._settings.timeout_seconds}s)"
            ) from exc
        except httpx.TransportError as exc:
            raise NightshiftUnavailableError(
                f"cannot reach nightshift at {self._base}: {self._redact(str(exc))}"
            ) from exc
        return response, int((time.monotonic() - started) * 1000)

    def _redact(self, text: str) -> str:
        token = self._settings.bearer_token()
        return text.replace(token, "[REDACTED]") if token else text

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        code, message = _error_details(response)
        detail = self._redact(message)[:MAX_ERROR_TEXT]
        suffix = f" ({code})" if code else ""
        if status in (401, 403):
            raise NightshiftAuthError(
                f"nightshift refused the token (HTTP {status}){suffix}: copy the current "
                "API key (Nightshift Console > API key) into NIGHTSHIFT_TOKEN",
                status_code=status,
                code=code,
            )
        if status == 429:
            raise NightshiftRateLimitedError(
                f"nightshift is rate limiting (HTTP 429){suffix}: {detail}",
                status_code=status,
                code=code,
            )
        if status >= 500:
            raise NightshiftProviderError(
                f"nightshift or the model behind the lane failed (HTTP {status}){suffix}: {detail}",
                status_code=status,
                code=code,
                detail=detail,
            )
        raise NightshiftRequestError(
            f"nightshift rejected the request (HTTP {status}){suffix}: {detail}",
            status_code=status,
            code=code,
            detail=detail,
        )

    @staticmethod
    def _json(response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError as exc:
            raise NightshiftResponseError(
                "nightshift returned a non-JSON response", status_code=response.status_code
            ) from exc

    # ------------------------------------------------------------------- API

    def list_models(self) -> list[str]:
        """Every model and routing id the runtime advertises."""
        response, _ = self._send("GET", MODELS_PATH, chat=False)
        self._raise_for_status(response)
        return _model_ids(self._json(response))

    def probe(self) -> ProbeEvidence:
        """Classify runtime status exactly as the provider guide prescribes.

        Runtime problems become a state, not an exception; only a broken local
        configuration raises.
        """
        endpoint = f"{self._base}{MODELS_PATH}"
        evidence = {"endpoint": endpoint, "app_id": self._settings.app_id}
        try:
            response, latency_ms = self._send("GET", MODELS_PATH, chat=False)
        except NightshiftUnavailableError as exc:
            return ProbeEvidence(**evidence, state=RuntimeState.OFFLINE, detail=str(exc))

        status = response.status_code
        if status in (401, 403):
            return ProbeEvidence(
                **evidence,
                state=RuntimeState.UNAUTHORIZED,
                http_status=status,
                latency_ms=latency_ms,
                detail="runtime is up but refused the token",
            )
        if status != 200:
            return ProbeEvidence(
                **evidence,
                state=RuntimeState.OFFLINE,
                http_status=status,
                latency_ms=latency_ms,
                detail=f"unexpected HTTP {status} from the models endpoint",
            )
        try:
            ids = _model_ids(response.json())
        except ValueError:
            ids = []
        if not any(model_id.startswith(ROUTING_MODE_PREFIX) for model_id in ids):
            return ProbeEvidence(
                **evidence,
                state=RuntimeState.OFFLINE,
                http_status=status,
                model_ids=ids,
                latency_ms=latency_ms,
                detail="answered 200 but listed no meterless/* ids; this is not a Nightshift runtime",
            )
        return ProbeEvidence(
            **evidence,
            state=RuntimeState.ONLINE,
            http_status=status,
            model_ids=ids,
            latency_ms=latency_ms,
        )

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        """One non-streaming chat completion on a lane or model id."""
        wire_messages = [message.model_dump() for message in messages]
        body: dict = {"model": model, "messages": wire_messages, "stream": False}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature

        call_id = str(uuid.uuid4())
        response, latency_ms = self._send("POST", CHAT_PATH, chat=True, json_body=body)
        self._raise_for_status(response)
        payload = self._json(response)
        if not isinstance(payload, dict):
            raise NightshiftResponseError("chat response is not a JSON object", status_code=200)

        content, finish_reason = _first_choice(payload)
        digest, prompt_chars = prompt_digest(wire_messages)
        served_model = payload.get("model")
        evidence = ChatCallEvidence(
            call_id=call_id,
            endpoint=f"{self._base}{CHAT_PATH}",
            app_id=self._settings.app_id,
            requested_model=model,
            served_model=None if served_model is None else str(served_model),
            receipt=RuntimeReceipt.from_payload(payload.get("meterless")),
            usage=_usage(payload.get("usage")),
            finish_reason=finish_reason,
            prompt_sha256=digest,
            prompt_chars=prompt_chars,
            response_chars=len(content),
            latency_ms=latency_ms,
        )
        return ChatResult(content=content, evidence=evidence)


# ---------------------------------------------------------------- parsing


def _model_ids(payload: object) -> list[str]:
    """Model ids from an OpenAI-style listing (``data`` list) or a bare list."""
    entries = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    ids = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(str(entry["id"]))
        elif isinstance(entry, str):
            ids.append(entry)
    return ids


def _first_choice(payload: dict) -> tuple[str, str | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise NightshiftResponseError("chat response has no choices", status_code=200)
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):  # content-part form: [{"type": "text", "text": ...}]
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    finish_reason = choice.get("finish_reason")
    return (content or ""), (None if finish_reason is None else str(finish_reason))


def _usage(payload: object) -> TokenUsage | None:
    if not isinstance(payload, dict):
        return None

    def count(key: str) -> int | None:
        value = payload.get(key)
        return value if isinstance(value, int) else None

    return TokenUsage(
        prompt_tokens=count("prompt_tokens"),
        completion_tokens=count("completion_tokens"),
        total_tokens=count("total_tokens"),
    )


def _error_details(response: httpx.Response) -> tuple[str | None, str]:
    """(machine code, message) from an OpenAI-style error body, if any."""
    try:
        payload = response.json()
    except ValueError:
        return None, response.text
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code") or error.get("type")
        return (None if code is None else str(code)), str(error.get("message", ""))
    return None, response.text
