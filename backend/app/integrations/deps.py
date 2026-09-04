"""FastAPI dependencies for service-account (API key) authentication.

Deliberately additive/parallel to `app.identity.deps` rather than a
change to it: `get_current_user`/`require_permission` keep authenticating
real human sessions exactly as before (zero risk of regressing Phases
1-9's routers, which all depend on getting a real `User` ORM object back
with real group-membership relationships). Service accounts authenticate
via `Authorization: Bearer <key_prefix>.<secret>` against this module's
own dependency, `require_scope`, and reach the API through the
integration-specific routes in `app.integrations.router` — see that
module's docstring and PHASE_10_VALIDATION_REPORT.md's "Architecture
Deviations" for why full endpoint-by-endpoint dual-auth across 9 prior
phases' routers was assessed as out of scope for this phase.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.models import ServiceAccount
from app.integrations.service import authenticate_service_account
from app.platform.db.session import get_session


async def get_current_service_account(
    request: Request, db: AsyncSession = Depends(get_session)
) -> ServiceAccount:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    api_key = header.removeprefix("Bearer ").strip()
    account = await authenticate_service_account(db, api_key)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await db.commit()  # persists last_used_at even though the caller may not commit again
    return account


def require_scope(code: str):
    """Dependency factory mirroring `app.identity.deps.require_permission`
    — 403s unless the authenticated service account was granted `code`.
    Scopes are literally `permissions.code` strings (Phase 1's RBAC
    vocabulary, reused verbatim, never a parallel scope namespace)."""

    async def _check(
        account: ServiceAccount = Depends(get_current_service_account),
    ) -> ServiceAccount:
        if code not in (account.scopes or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"service account lacks required scope: {code}",
            )
        return account

    return _check
