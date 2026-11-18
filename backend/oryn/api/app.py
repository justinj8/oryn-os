from fastapi import FastAPI

from oryn import __version__
from oryn.api.routes import admin, auth, events
from oryn.core.config import get_settings
from oryn.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Oryn OS", version=__version__)

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": __version__,
            "llm_provider": get_settings().effective_llm_provider,
        }

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(events.router)
    return app
