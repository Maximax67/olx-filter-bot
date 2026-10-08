from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.container import Container
from src.infrastructure.config import Environment, Settings, load_settings
from src.infrastructure.logging import configure_logging
from src.presentation.api.router import api_router

SHOW_DOCS_IN = frozenset({Environment.LOCAL, Environment.STAGING})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    container: Container = app.state.container
    await container.close()


def create_app(
    settings: Settings | None = None, *, container: Container | None = None
) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.logging)

    app_kwargs: dict[str, Any] = {
        "title": "OLX Filter Bot",
        "version": "0.1.0",
        "description": "Telegram webhook and cron endpoints for the OLX filter bot.",
        "lifespan": lifespan,
    }
    if settings.app.environment in SHOW_DOCS_IN:
        app_kwargs.update(
            docs_url="/api/docs",
            redoc_url="/api/redoc",
            openapi_url="/api/openapi.json",
        )
    else:
        app_kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)

    app = FastAPI(**app_kwargs)
    app.state.container = container or Container(settings)
    app.include_router(api_router, prefix="/api")
    return app
