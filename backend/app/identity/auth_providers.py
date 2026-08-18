"""Authentication provider interface, analogous to `app.providers` (the
Speech/Diarization/LLM/Storage interface+implementation pattern).

Only `LocalAuthProvider` is a real implementation in Phase 1. `OIDC`,
`LDAP_AD`, and `REVERSE_PROXY` are represented only as
`AuthProviderType` values so `users.auth_provider` and callers written
against `AuthProvider` never need to change shape when those providers are
implemented in a later phase — they will each get their own
`AuthProvider` subclass here, selected by configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import AuthProviderType, User
from app.identity.passwords import verify_password


@dataclass(frozen=True)
class AuthenticationResult:
    """Successful authentication outcome, provider-agnostic."""

    user: User


class AuthProvider(ABC):
    """One identity provider. `authenticate` returns `None` on any failure
    (unknown user, wrong credentials, inactive account, wrong provider) —
    callers must not distinguish these cases in user-facing responses
    (avoid username enumeration), though the caller may log the specific
    reason to the audit trail."""

    provider_type: ClassVar[AuthProviderType]

    @abstractmethod
    async def authenticate(
        self, session: AsyncSession, **credentials: str
    ) -> AuthenticationResult | None:
        raise NotImplementedError


class LocalAuthProvider(AuthProvider):
    """Username/password authentication against the local `users` table."""

    provider_type = AuthProviderType.LOCAL

    async def authenticate(
        self, session: AsyncSession, **credentials: str
    ) -> AuthenticationResult | None:
        username = credentials["username"]
        password = credentials["password"]
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None:
            return None
        if user.auth_provider != AuthProviderType.LOCAL.value:
            return None
        if not user.is_active:
            return None
        if user.password_hash is None:
            return None
        if not verify_password(password, user.password_hash):
            return None

        return AuthenticationResult(user=user)
