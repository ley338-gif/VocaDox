"""Integration tests for POST /auth/login, POST /auth/logout, GET /auth/me
via the httpx-based ASGI test client (existing Phase 0 pattern), with the
DB and cache dependencies overridden to SQLite + an in-memory fake cache
so no external services are required."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from app.core.app_factory import create_app
from app.identity.deps import get_cache_backend
from app.identity.seed import apply_seed
from app.identity.service import (
    add_user_to_group,
    assign_role_to_group,
    create_local_user,
    get_or_create_group,
    get_role_by_name,
    get_user_by_username,
)
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import Base, get_session
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.identity.conftest import FakeCacheBackend


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _get_session_override() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    cache = FakeCacheBackend()

    app = create_app()
    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_cache_backend] = lambda: cache

    # Seed roles/permissions and one active local user, "alice".
    async with sessionmaker() as session:
        await apply_seed(session)
        await create_local_user(
            session,
            username="alice",
            password="a very strong password 123",
            display_name="Alice",
            email="alice@example.org",
        )
        role = await get_role_by_name(session, "User")
        assert role is not None
        group = await get_or_create_group(session, name="Clinicians")
        await assign_role_to_group(session, group_id=group.id, role_id=role.id)
        alice = await get_user_by_username(session, "alice")
        assert alice is not None
        await add_user_to_group(session, user_id=alice.id, group_id=group.id)
        await session.commit()

    transport = ASGITransport(app=app)
    # https:// (not http://) so httpx's cookie jar will actually attach the
    # session cookie on subsequent requests — it carries the `Secure`
    # attribute by default (settings.session_cookie_secure), matching
    # production, and http.cookiejar-based clients refuse to send Secure
    # cookies over a plain-http connection.
    async with AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client

    await engine.dispose()


async def test_login_succeeds_with_correct_credentials(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert "csrf_token" in body
    assert "vocadox_session" in response.cookies


async def test_login_fails_with_wrong_password(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401
    assert "vocadox_session" not in response.cookies


async def test_me_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_login_then_me_returns_permissions(api_client: AsyncClient) -> None:
    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    assert login_response.status_code == 200

    me_response = await api_client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    body = me_response.json()
    assert body["username"] == "alice"
    assert "conversation:create" in body["permissions"]
    assert "system:admin" not in body["permissions"]


async def test_csrf_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/csrf")
    assert response.status_code == 401


async def test_csrf_returns_same_token_as_login(api_client: AsyncClient) -> None:
    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    login_token = login_response.json()["csrf_token"]

    csrf_response = await api_client.get("/api/v1/auth/csrf")
    assert csrf_response.status_code == 200
    assert csrf_response.json()["csrf_token"] == login_token


async def test_csrf_token_from_recovery_endpoint_works_for_mutations(
    api_client: AsyncClient,
) -> None:
    await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    recovered_token = (await api_client.get("/api/v1/auth/csrf")).json()["csrf_token"]

    logout_response = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": recovered_token}
    )
    assert logout_response.status_code == 204


async def test_logout_without_csrf_header_is_rejected(api_client: AsyncClient) -> None:
    await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    response = await api_client.post("/api/v1/auth/logout")
    assert response.status_code == 403


async def test_logout_with_wrong_csrf_token_is_rejected(api_client: AsyncClient) -> None:
    await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    response = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": "not-the-right-token"}
    )
    assert response.status_code == 403


async def test_logout_invalidates_session(api_client: AsyncClient) -> None:
    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    csrf_token = login_response.json()["csrf_token"]

    logout_response = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
    )
    assert logout_response.status_code == 204

    me_response = await api_client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


async def test_login_rejects_inactive_user_and_does_not_leak_reason(
    api_client: AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/auth/login", json={"username": "no-such-user", "password": "irrelevant"}
    )
    unknown_body = response.json()

    wrong_pw_response = await api_client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "definitely-wrong"}
    )
    wrong_pw_body = wrong_pw_response.json()

    assert response.status_code == wrong_pw_response.status_code == 401
    assert unknown_body == wrong_pw_body  # identical generic error, no enumeration
