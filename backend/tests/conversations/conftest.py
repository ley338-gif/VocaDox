"""Shared fixtures for conversation/media domain tests: an httpx client
wired to an in-memory SQLite DB + fake Valkey cache (same pattern as
tests/identity/test_api_auth.py), with two organizations and one user per
organization already seeded so cross-organization authorization tests
don't need to repeat the setup.

All audio bytes used across these tests are synthetically generated at
test time (silence/sine-wave PCM written via the stdlib `wave` module, or
minimal valid container headers) — never a real recording of a real
person. See `make_wav_bytes` / the format-specific fixtures in
tests/media/test_validation.py for provenance of each synthetic sample.
"""

from __future__ import annotations

import io
import math
import struct
import wave
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
)
from app.organizations.models import Organization, OrganizationMembership
from app.platform.db import model_registry  # noqa: F401
from app.platform.db.session import Base, get_session
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tests.identity.conftest import FakeCacheBackend


def make_wav_bytes(*, duration_s: float = 0.2, sample_rate: int = 8000) -> bytes:
    """A short synthetic 440Hz sine-wave mono PCM WAV — generated, not recorded."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            value = int(3000 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            frames += struct.pack("<h", value)
        wav_file.writeframes(bytes(frames))
    return buf.getvalue()


@pytest_asyncio.fixture
async def app_env():
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

    yield app, sessionmaker
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(app_env):
    app, sessionmaker = app_env
    ids: dict[str, str] = {}
    async with sessionmaker() as session:
        await apply_seed(session)

        org_a = Organization(name="Org A", slug="org-a")
        org_b = Organization(name="Org B", slug="org-b")
        session.add_all([org_a, org_b])
        await session.flush()
        ids["org_a"] = str(org_a.id)
        ids["org_b"] = str(org_b.id)

        user_role = await get_role_by_name(session, "User")
        assert user_role is not None

        alice = await create_local_user(
            session, username="alice", password="a very strong password 123", display_name="Alice"
        )
        alice_group = await get_or_create_group(session, name="Org A Clinicians")
        await assign_role_to_group(session, group_id=alice_group.id, role_id=user_role.id)
        await add_user_to_group(session, user_id=alice.id, group_id=alice_group.id)
        session.add(OrganizationMembership(user_id=alice.id, organization_id=org_a.id))
        ids["alice_id"] = str(alice.id)

        bob = await create_local_user(
            session, username="bob", password="another very strong pw 456", display_name="Bob"
        )
        bob_group = await get_or_create_group(session, name="Org B Clinicians")
        await assign_role_to_group(session, group_id=bob_group.id, role_id=user_role.id)
        await add_user_to_group(session, user_id=bob.id, group_id=bob_group.id)
        session.add(OrganizationMembership(user_id=bob.id, organization_id=org_b.id))
        ids["bob_id"] = str(bob.id)

        admin_role = await get_role_by_name(session, "System Admin")
        assert admin_role is not None
        carol = await create_local_user(
            session, username="carol", password="yet another strong pw 789", display_name="Carol"
        )
        admin_group = await get_or_create_group(session, name="Admins")
        await assign_role_to_group(session, group_id=admin_group.id, role_id=admin_role.id)
        await add_user_to_group(session, user_id=carol.id, group_id=admin_group.id)
        ids["carol_id"] = str(carol.id)

        await session.commit()

    return ids


@pytest_asyncio.fixture
async def client(app_env) -> AsyncIterator[AsyncClient]:
    app, _ = app_env
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
        yield ac


async def login(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}
