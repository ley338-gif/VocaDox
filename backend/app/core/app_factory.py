"""FastAPI application factory.

Phase 0 wires only cross-cutting platform concerns (health, logging, request
id, CORS, OpenAPI). No domain routers exist yet — they are registered here
starting Phase 1+.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.platform.config import get_settings
from app.platform.health import router as health_router
from app.platform.logging import configure_logging
from app.platform.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        description="On-premise evidence-based conversation documentation platform.",
        version="0.0.1",
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)

    return app
