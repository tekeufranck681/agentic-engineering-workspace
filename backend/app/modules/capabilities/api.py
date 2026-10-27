"""FastAPI wiring for the capability runtime: shared instance, ports, error mapping.

The runtime is built once per process on the shared ModelGateway and the
shared H-MEM provider, so missing model configuration still fails closed with
the gateway's 503, and an unreachable engine with 503 for contracts that
recall memory. Capability failures answer with their stable ``kind``.
"""

import uuid
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.modules.capabilities.contract import InvocationContext
from app.modules.capabilities.errors import (
    CapabilityBudgetError,
    CapabilityCancelledError,
    CapabilityError,
    CapabilityInputError,
    CapabilityMemoryError,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
)
from app.modules.capabilities.registry import ARCHITECTURE_DESIGN, REQUIREMENTS_ANALYZE, default_registry
from app.modules.capabilities.runtime import CapabilityPort, CapabilityRuntime
from app.modules.memory.api import get_memory_provider, get_memory_settings
from app.modules.model_gateway.api import RETRY_AFTER_SECONDS, get_model_gateway

# Anything not listed (an output that stayed invalid) is a bad answer from upstream: 502.
_STATUS: tuple[tuple[type[CapabilityError], int], ...] = (
    (CapabilityTimeoutError, 504),
    (CapabilityMemoryError, 503),
    (CapabilityBudgetError, 429),
    (CapabilityCancelledError, 409),
    (CapabilityInputError, 422),
    (CapabilityNotFoundError, 500),
)


@lru_cache
def get_capability_runtime() -> CapabilityRuntime:
    """Process-wide runtime on the shared gateway and memory. A failed build is not cached."""
    settings = get_memory_settings()
    return CapabilityRuntime(
        get_model_gateway(),
        default_registry(),
        memory=get_memory_provider(),
        recall_top_n=settings.recall_top_n,
        recall_threshold=settings.recall_threshold,
    )


def requirements_capability() -> CapabilityPort:
    """LLMPort for M4's requirements service."""
    return get_capability_runtime().port(REQUIREMENTS_ANALYZE)


async def architecture_capability(request: Request) -> CapabilityPort:
    """LLMPort for M4's architecture service (architecture, ADRs, contracts).

    Bound to the request's project, so the contract's H-MEM recall reads that
    project's lessons and the receipts name the project.
    """
    context = InvocationContext(project_id=await request_project_id(request))
    return get_capability_runtime().port(ARCHITECTURE_DESIGN, context)


async def request_project_id(request: Request) -> str | None:
    """The ``project_id`` of a JSON request body, when it is a UUID.

    FastAPI has already read and parsed the body for the endpoint; Starlette
    caches it, so this reads no extra bytes.
    """
    if request.method not in ("POST", "PUT", "PATCH"):
        return None
    try:
        body = await request.json()
    except ValueError:
        return None
    value = body.get("project_id") if isinstance(body, dict) else None
    try:
        return str(uuid.UUID(str(value))) if value is not None else None
    except ValueError:
        return None


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
