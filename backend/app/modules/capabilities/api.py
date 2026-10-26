"""FastAPI wiring for the capability runtime: shared instance, ports, error mapping.

The runtime is built once per process on the shared ModelGateway, so missing
model configuration still fails closed with the gateway's 503. Capability
failures answer with their stable ``kind``.
"""

from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.modules.capabilities.errors import (
    CapabilityCancelledError,
    CapabilityError,
    CapabilityInputError,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
)
from app.modules.capabilities.registry import ARCHITECTURE_DESIGN, REQUIREMENTS_ANALYZE, default_registry
from app.modules.capabilities.runtime import CapabilityPort, CapabilityRuntime
from app.modules.model_gateway.api import RETRY_AFTER_SECONDS, get_model_gateway

# Anything not listed (an output that stayed invalid) is a bad answer from upstream: 502.
_STATUS: tuple[tuple[type[CapabilityError], int], ...] = (
    (CapabilityTimeoutError, 504),
    (CapabilityCancelledError, 409),
    (CapabilityInputError, 422),
    (CapabilityNotFoundError, 500),
)


@lru_cache
def get_capability_runtime() -> CapabilityRuntime:
    """Process-wide runtime on the shared gateway. A failed build is not cached."""
    return CapabilityRuntime(get_model_gateway(), default_registry())


def requirements_capability() -> CapabilityPort:
    """LLMPort for M4's requirements service."""
    return get_capability_runtime().port(REQUIREMENTS_ANALYZE)


def architecture_capability() -> CapabilityPort:
    """LLMPort for M4's architecture service (architecture, ADRs, contracts)."""
    return get_capability_runtime().port(ARCHITECTURE_DESIGN)


def install_capability_error_handlers(app: FastAPI) -> None:
    """Answer capability failures with a classified JSON error instead of a bare 500."""

    @app.exception_handler(CapabilityError)
    async def _capability_error(request: Request, exc: CapabilityError) -> JSONResponse:
        status = next((code for error_type, code in _STATUS if isinstance(exc, error_type)), 502)
        headers = {"Retry-After": str(RETRY_AFTER_SECONDS)} if exc.retryable else None
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "kind": exc.kind,
                    "message": str(exc),
                    "retryable": exc.retryable,
                    "capability": exc.capability,
                    "invocation_id": exc.invocation_id,
                }
            },
            headers=headers,
        )
