"""Tests for the local authentication provider (part of the multi-provider
AuthProvider interface — LOCAL is the only real implementation in Phase 1)."""

from __future__ import annotations

from app.identity.auth_providers import LocalAuthProvider
from app.identity.models import AuthProviderType, User
from app.identity.passwords import hash_password
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_local_user(
    db_session: AsyncSession,
    *,
    username: str = "alice",
    password: str = "correct horse battery",
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        display_name=username,
        password_hash=hash_password(password),
        auth_provider=AuthProviderType.LOCAL.value,
        is_active=is_active,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_authenticate_succeeds_with_correct_credentials(db_session: AsyncSession) -> None:
    user = await _make_local_user(db_session, password="correct horse battery")
    provider = LocalAuthProvider()

    result = await provider.authenticate(
        db_session, username="alice", password="correct horse battery"
    )

    assert result is not None
    assert result.user.id == user.id


async def test_authenticate_fails_with_wrong_password(db_session: AsyncSession) -> None:
    await _make_local_user(db_session, password="correct horse battery")
    provider = LocalAuthProvider()

    result = await provider.authenticate(db_session, username="alice", password="wrong password")

    assert result is None


async def test_authenticate_fails_for_unknown_username(db_session: AsyncSession) -> None:
    provider = LocalAuthProvider()
    result = await provider.authenticate(db_session, username="ghost", password="anything at all")
    assert result is None


async def test_authenticate_fails_for_inactive_user(db_session: AsyncSession) -> None:
    await _make_local_user(db_session, password="correct horse battery", is_active=False)
    provider = LocalAuthProvider()

    result = await provider.authenticate(
        db_session, username="alice", password="correct horse battery"
    )

    assert result is None


async def test_authenticate_fails_for_non_local_provider_user(db_session: AsyncSession) -> None:
    user = User(
        username="oidc-alice",
        display_name="OIDC Alice",
        password_hash=None,
        auth_provider=AuthProviderType.OIDC.value,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    provider = LocalAuthProvider()
    result = await provider.authenticate(db_session, username="oidc-alice", password="anything")

    assert result is None
