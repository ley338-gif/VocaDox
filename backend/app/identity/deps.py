"""FastAPI dependencies for authentication, sessions, and permission
enforcement.

Per the threat model, every domain router from Phase 1 onward sits behind
authentication by default; `get_current_user` (or `require_permission`) is
the dependency other domains' routers should use once they exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.identity.sessions import CSRF_HEADER_NAME, SESSION_COOKIE_NAME, SessionData, SessionStore
from app.platform.db.session import get_session
from app.platform.valkey.backends import CacheBackend
from app.platform.valkey.valkey_backend import get_valkey_backend

# get_valkey_backend returns a concrete ValkeyBackend, but every call site
# here type-hints against the CacheBackend Protocol only (see
# tests/test_architecture_boundaries.py — importing app.platform.valkey is
# permitted, importing the `valkey` client package itself is not).


def get_cache_backend() -> CacheBackend:
    return get_valkey_backend()


def get_session_store(cache: CacheBackend = Depends(get_cache_backend)) -> SessionStore:
    from app.platform.config import get_settings

    return SessionStore(cache, ttl_seconds=get_settings().session_ttl_seconds)


async def get_current_session(
    request: Request,
    store: SessionStore = Depends(get_session_store),
) -> SessionData:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    session_data = await store.get(session_id)
    if session_data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    return session_data


async def get_current_user(
    session_data: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_session),
) -> User:
    result = await db.execute(select(User).where(User.id == uuid.UUID(session_data.user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


def require_csrf(
    request: Request,
    session_data: SessionData = Depends(get_current_session),
) -> None:
    """Synchronizer-token CSRF check for state-changing requests. The
    session cookie is httponly (unreadable by JS or an attacker page); the
    caller must additionally echo the CSRF token — handed to it once, in
    the login response body, and never set as a readable cookie — in the
    `X-CSRF-Token` header. A cross-site request can rely on the browser
    auto-attaching the session cookie but has no way to read or replay the
    header value, since it never touches a cookie."""
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not header_token or header_token != session_data.csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")


def require_permission(code: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: returns a dependency that 403s unless the
    current user has permission `code`, per genuine permission-based RBAC
    (spec) — never a role-name string comparison."""

    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        permissions = await get_user_permissions(db, user.id)
        if code not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return user

    return _check
