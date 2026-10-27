"""FastAPI application factory (ENG-009, owned by M4).

Boots the workspace backend: configures logging, mounts every module router,
and exposes a health check. Module routers live under app/modules/*; this file
is wiring only.
"""

from fastapi import FastAPI

from app.core.logging import setup_logging
from app.modules.capabilities.api import install_capability_error_handlers
from app.modules.context.api import install_context_error_handlers
from app.modules.context.api import router as context_router
from app.modules.integrations.router import router as integrations_router
from app.modules.memory.api import install_memory_error_handlers
from app.modules.memory.api import router as memory_router
from app.modules.model_gateway.api import install_model_error_handlers
from app.modules.architecture.router import router as architecture_router
from app.modules.persistence.router import router as persistence_router
from app.modules.requirements.router import router as requirements_router
from app.modules.architecture.router import router as architecture_router
from app.modules.planning.router import router as planning_router
from app.modules.runs.sse import router as runs_sse_router
from app.modules.runs.router import router as runs_router
from app.modules.delivery.router import router as delivery_router


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="Agentic Engineering Workspace",
        description="AI engineering teammate — requirements through delivery.",
        version="0.1.0",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(persistence_router)
    app.include_router(requirements_router)
    app.include_router(architecture_router)
    app.include_router(planning_router)
    app.include_router(runs_router)
    app.include_router(delivery_router)
    app.include_router(runs_sse_router)
    app.include_router(runs_sse_router)
    app.include_router(memory_router)
    app.include_router(context_router)
    app.include_router(integrations_router)
    install_model_error_handlers(app)
    install_capability_error_handlers(app)
    install_memory_error_handlers(app)
    install_context_error_handlers(app)
    return app


app = create_app()
