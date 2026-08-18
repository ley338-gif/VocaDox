"""Tests for the one-time bootstrap-admin CLI, including the "refuses to
run twice" guard (spec §66: no direct DB manipulation for the first
admin, and the bootstrap path must not be silently reusable)."""

from __future__ import annotations

import pytest
from app.identity.bootstrap_admin import bootstrap_admin
from app.identity.service import get_user_by_username
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _patch_sessionmaker(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """bootstrap_admin() opens its own session via get_sessionmaker(); for
    the test we hand it a sessionmaker bound to the same in-memory SQLite
    engine backing `db_session` so assertions can see the same rows."""

    # db_session is used as an async context manager (`async with
    # sessionmaker() as session`) inside bootstrap_admin; wrap it so
    # `__aenter__`/`__aexit__` don't close the shared fixture session
    # (each test commits multiple times against the same in-memory DB).
    class _NoCloseWrapper:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(
        "app.identity.bootstrap_admin.get_sessionmaker", lambda: (lambda: _NoCloseWrapper())
    )


async def test_bootstrap_creates_first_admin(db_session: AsyncSession) -> None:
    exit_code = await bootstrap_admin(
        username="admin",
        password="a very strong password 123",
        display_name="Administrator",
        email="admin@example.org",
        force=False,
    )
    assert exit_code == 0

    user = await get_user_by_username(db_session, "admin")
    assert user is not None
    assert user.email == "admin@example.org"


async def test_bootstrap_refuses_second_run_without_force(db_session: AsyncSession) -> None:
    first = await bootstrap_admin(
        username="admin",
        password="a very strong password 123",
        display_name="Administrator",
        email=None,
        force=False,
    )
    assert first == 0

    second = await bootstrap_admin(
        username="admin2",
        password="another strong password 456",
        display_name="Second Admin",
        email=None,
        force=False,
    )
    assert second == 1
    assert await get_user_by_username(db_session, "admin2") is None


async def test_bootstrap_allows_second_run_with_force(db_session: AsyncSession) -> None:
    first = await bootstrap_admin(
        username="admin",
        password="a very strong password 123",
        display_name="Administrator",
        email=None,
        force=False,
    )
    assert first == 0

    second = await bootstrap_admin(
        username="admin2",
        password="another strong password 456",
        display_name="Second Admin",
        email=None,
        force=True,
    )
    assert second == 0
    assert await get_user_by_username(db_session, "admin2") is not None


async def test_bootstrap_refuses_duplicate_username(db_session: AsyncSession) -> None:
    first = await bootstrap_admin(
        username="admin",
        password="a very strong password 123",
        display_name="Administrator",
        email=None,
        force=False,
    )
    assert first == 0

    duplicate = await bootstrap_admin(
        username="admin",
        password="yet another strong password",
        display_name="Duplicate",
        email=None,
        force=True,
    )
    assert duplicate == 1
