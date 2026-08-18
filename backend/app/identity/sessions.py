"""Server-side session store, built on the existing `CacheBackend`
Protocol (Valkey-backed in production — see
docs/architecture/adr/0009-session-storage.md for why sessions live here
rather than in a Postgres table).

This module only depends on `app.platform.valkey.backends.CacheBackend`
(a `Protocol`), never on `valkey` or a concrete backend class, per the
domain/platform boundary enforced by
`tests/test_architecture_boundaries.py`.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from app.platform.valkey.backends import CacheBackend

SESSION_COOKIE_NAME = "vocadox_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SESSION_KEY_PREFIX = "identity:session:"


@dataclass(frozen=True)
class SessionData:
    session_id: str
    user_id: str
    username: str
    csrf_token: str
    created_at: str
    expires_at: str
    ip_address: str | None
    user_agent: str | None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return now >= datetime.fromisoformat(self.expires_at)


class SessionStore:
    """Thin wrapper over `CacheBackend` implementing session
    create/read/delete with absolute expiry. Sessions are opaque
    server-generated tokens (`secrets.token_urlsafe`) — never derived from,
    or containing, user-identifying data, so a leaked cookie alone reveals
    nothing about the user."""

    def __init__(self, cache: CacheBackend, *, ttl_seconds: int) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        username: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SessionData:
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        data = SessionData(
            session_id=session_id,
            user_id=str(user_id),
            username=username,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self._ttl_seconds)).isoformat(),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._cache.set(
            _SESSION_KEY_PREFIX + session_id,
            json.dumps(asdict(data)),
            ttl_seconds=self._ttl_seconds,
        )
        return data

    async def get(self, session_id: str) -> SessionData | None:
        if not session_id:
            return None
        raw = await self._cache.get(_SESSION_KEY_PREFIX + session_id)
        if raw is None:
            return None
        data = SessionData(**json.loads(raw))
        if data.is_expired():
            await self.delete(session_id)
            return None
        return data

    async def delete(self, session_id: str) -> None:
        await self._cache.delete(_SESSION_KEY_PREFIX + session_id)
