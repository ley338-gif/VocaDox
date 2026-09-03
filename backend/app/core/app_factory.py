"""FastAPI application factory.

Phase 0 wired only cross-cutting platform concerns (health, logging, request
id, CORS, OpenAPI). Phase 1 adds the first domain router (identity/auth).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.administration.router import router as administration_router
from app.conversations.router import router as conversations_router
from app.diarization.router import router as diarization_router
from app.identity.router import router as identity_router
from app.intelligence.router import router as intelligence_router
from app.organizations.router import router as organizations_router
from app.platform.config import get_settings
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.health import router as health_router
from app.platform.logging import configure_logging
from app.platform.middleware import RequestIdMiddleware
from app.platform.version import APPLICATION_VERSION
from app.transcription.router import router as transcription_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        description="On-premise evidence-based conversation documentation platform.",
        version=APPLICATION_VERSION,
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
    app.include_router(identity_router, prefix=settings.api_prefix)
    app.include_router(conversations_router, prefix=settings.api_prefix)
    app.include_router(organizations_router, prefix=settings.api_prefix)
    app.include_router(transcription_router, prefix=settings.api_prefix)
    app.include_router(diarization_router, prefix=settings.api_prefix)
    app.include_router(intelligence_router, prefix=settings.api_prefix)
    app.include_router(administration_router, prefix=settings.api_prefix)

    return app
