"""Typed ModelGateway failures, independent of the provider behind it.

Capabilities catch these, never provider exceptions. ``kind`` is a stable code
for API errors and receipts; ``retryable`` marks failures a retry policy may
repeat, while everything else needs a fix. Messages never carry the runtime
token or prompt text.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.model_gateway.receipts import ModelCallReceipt


class ModelGatewayError(Exception):
    """Base class for gateway failures."""

    kind = "model_error"
    retryable = False
    receipt: "ModelCallReceipt | None" = None
    """Set by the gateway: the receipt of the failed call."""

    def __init__(self, message: str, *, retryable: bool | None = None, code: str | None = None) -> None:
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable
        self.code = code


class ModelConfigError(ModelGatewayError):
    """The gateway or its provider is not configured (missing token, bad lane)."""

    kind = "model_config"


class ModelAuthError(ModelGatewayError):
    """The provider refused the credentials."""

    kind = "model_auth"


class ModelUnavailableError(ModelGatewayError):
    """The provider is unreachable or timed out."""

    kind = "model_unavailable"
    retryable = True


class ModelRateLimitedError(ModelGatewayError):
    """The provider is throttling (HTTP 429)."""

    kind = "model_rate_limited"
    retryable = True


class ModelProviderError(ModelGatewayError):
    """The provider or the model behind the lane failed (HTTP 5xx)."""

    kind = "model_provider_error"
    retryable = True


class ModelRequestError(ModelGatewayError):
    """The provider rejected the request: unknown lane or model, bad input."""

    kind = "model_request_rejected"


class ModelResponseError(ModelGatewayError):
    """The provider answered with a body that is not a usable completion."""

    kind = "model_bad_response"


class StructuredOutputError(ModelGatewayError):
    """The reply is not valid JSON for the requested schema.

    ``reply_text`` keeps the raw reply for a bounded repair attempt (ENG-028);
    it is never part of the message, the logs or the receipts.
    """

    kind = "model_structured_output_invalid"

    def __init__(self, message: str, *, reply_text: str = "") -> None:
        super().__init__(message)
        self.reply_text = reply_text
