"""Async engine and session factory, built on SQLAlchemy 2.0 + asyncpg."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.platform.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models (none defined yet)."""


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide async SQLAlchemy engine (created once)."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url, echo=settings.database_echo, pool_pre_ping=True
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped AsyncSession."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def check_database_connectivity() -> bool:
    """Used by the readiness probe. Returns True iff a trivial query succeeds."""
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness probe must not raise
        return False
