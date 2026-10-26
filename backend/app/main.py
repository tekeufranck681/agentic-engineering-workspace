"""FastAPI application factory (ENG-009, owned by M4).

Boots the workspace backend: configures logging, mounts every module router,
and exposes a health check. Module routers live under app/modules/*; this file
is wiring only.
"""

from fastapi import FastAPI

from app.core.logging import setup_logging
from app.modules.model_gateway.api import install_model_error_handlers
from app.modules.persistence.router import router as persistence_router
from app.modules.requirements.router import router as requirements_router


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
    install_model_error_handlers(app)
    return app


app = create_app()
