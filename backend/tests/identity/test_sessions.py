"""Unit tests for the Valkey-CacheBackend-based session store."""

from __future__ import annotations

import uuid

from app.identity.sessions import SessionStore

from tests.identity.conftest import FakeCacheBackend


async def test_create_and_get_session(fake_cache: FakeCacheBackend) -> None:
    store = SessionStore(fake_cache, ttl_seconds=60)
    user_id = uuid.uuid4()
    created = await store.create(
        user_id=user_id, username="alice", ip_address="127.0.0.1", user_agent="pytest"
    )

    fetched = await store.get(created.session_id)
    assert fetched is not None
    assert fetched.user_id == str(user_id)
    assert fetched.username == "alice"
    assert fetched.csrf_token == created.csrf_token


async def test_get_unknown_session_returns_none(fake_cache: FakeCacheBackend) -> None:
    store = SessionStore(fake_cache, ttl_seconds=60)
    assert await store.get("does-not-exist") is None


async def test_get_empty_session_id_returns_none(fake_cache: FakeCacheBackend) -> None:
    store = SessionStore(fake_cache, ttl_seconds=60)
    assert await store.get("") is None


async def test_delete_invalidates_session(fake_cache: FakeCacheBackend) -> None:
    store = SessionStore(fake_cache, ttl_seconds=60)
    created = await store.create(
        user_id=uuid.uuid4(), username="alice", ip_address=None, user_agent=None
    )
    await store.delete(created.session_id)
    assert await store.get(created.session_id) is None


async def test_session_expires_after_ttl(fake_cache: FakeCacheBackend) -> None:
    # ttl_seconds=0 means the underlying CacheBackend entry is already
    # expired the instant it's read back.
    store = SessionStore(fake_cache, ttl_seconds=0)
    created = await store.create(
        user_id=uuid.uuid4(), username="alice", ip_address=None, user_agent=None
    )
    assert await store.get(created.session_id) is None


async def test_two_sessions_for_same_user_have_different_ids_and_csrf_tokens(
    fake_cache: FakeCacheBackend,
) -> None:
    store = SessionStore(fake_cache, ttl_seconds=60)
    user_id = uuid.uuid4()
    first = await store.create(user_id=user_id, username="alice", ip_address=None, user_agent=None)
    second = await store.create(user_id=user_id, username="alice", ip_address=None, user_agent=None)
    assert first.session_id != second.session_id
    assert first.csrf_token != second.csrf_token
