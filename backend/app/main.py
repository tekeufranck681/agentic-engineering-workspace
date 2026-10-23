"""FastAPI application factory (PROVISIONAL — M4's ENG-009 will own this).

Exists so the M2 persistence router can run and be tested in isolation; when
the real bootstrap lands it replaces this file and mounts the same router.
"""

from fastapi import FastAPI

from app.modules.persistence.router import router as persistence_router


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Engineering Workspace (M2 dev slice)")

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(persistence_router)
    return app


app = create_app()
