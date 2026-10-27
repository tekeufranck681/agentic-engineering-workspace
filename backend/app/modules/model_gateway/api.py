"""FastAPI wiring for the ModelGateway: shared instance, capability ports, errors.

The gateway is built once per process from the NIGHTSHIFT_* and
MODEL_GATEWAY_* settings. Missing configuration fails closed: the dependency
raises ModelConfigError and the handler answers 503, so no endpoint ever
answers from a fake model. Restart the process after rotating the token.
"""

from functools import lru_cache

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.modules.model_gateway.config import ModelGatewaySettings
from app.modules.model_gateway.errors import (
    ModelAuthError,
    ModelConfigError,
    ModelGatewayError,
    ModelLaneUnavailableError,
    ModelRateLimitedError,
    ModelUnavailableError,
)
from app.modules.model_gateway.gateway import ModelGateway
from app.modules.model_gateway.provider import NightshiftProvider
from app.modules.model_gateway.receipts import ReceiptSink
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import NightshiftConfigError

# The model dependency is down or misconfigured: 503. The model or provider
# produced something unusable: 502.
_UNAVAILABLE = (
    ModelConfigError,
    ModelAuthError,
    ModelUnavailableError,
    ModelRateLimitedError,
    ModelLaneUnavailableError,
)
RETRY_AFTER_SECONDS = 30


def build_model_gateway(
    nightshift_settings: NightshiftSettings | None = None,
    gateway_settings: ModelGatewaySettings | None = None,
    sink: ReceiptSink | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ModelGateway:
    """A gateway on the Nightshift provider; raises ModelConfigError when unusable."""
    try:
        nightshift = nightshift_settings if nightshift_settings is not None else NightshiftSettings.from_env()
        routing = gateway_settings if gateway_settings is not None else ModelGatewaySettings()
    except NightshiftConfigError as exc:
        raise ModelConfigError(f"nightshift: {exc}") from exc
    except ValueError as exc:  # invalid MODEL_GATEWAY_* values (pydantic ValidationError)
        raise ModelConfigError(f"invalid model gateway configuration: {exc}") from exc
    return ModelGateway(NightshiftProvider.from_settings(nightshift, transport=transport), routing, sink)


@lru_cache
def get_model_gateway() -> ModelGateway:
    """Process-wide gateway. A failed build is not cached. Capabilities reach it
    through the capability runtime (``app.modules.capabilities.api``)."""
    return build_model_gateway()


def install_model_error_handlers(app: FastAPI) -> None:
    """Answer gateway failures with a classified JSON error instead of a bare 500."""

    @app.exception_handler(ModelGatewayError)
    async def _model_error(request: Request, exc: ModelGatewayError) -> JSONResponse:
        status = 503 if isinstance(exc, _UNAVAILABLE) else 502
        headers = {"Retry-After": str(RETRY_AFTER_SECONDS)} if exc.retryable else None
        return JSONResponse(
            status_code=status,
            content={"error": {"kind": exc.kind, "message": str(exc), "retryable": exc.retryable}},
            headers=headers,
        )
