"""Fixtures shared by identity-domain tests: an in-memory SQLite database
(schema built straight from `Base.metadata`, no Postgres required — matches
the existing "no external services needed at test time" convention) and an
in-memory fake `CacheBackend` standing in for Valkey."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest_asyncio
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import Base
from app.platform.valkey.backends import CacheBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


class FakeCacheBackend(CacheBackend):
    """Minimal in-process stand-in for Valkey's CacheBackend, honoring TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def fake_cache() -> FakeCacheBackend:
    return FakeCacheBackend()
