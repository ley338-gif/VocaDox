"""Authentication REST endpoints: POST /auth/login, POST /auth/logout,
GET /auth/me."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.identity.auth_providers import LocalAuthProvider
from app.identity.deps import (
    get_current_session,
    get_current_user,
    get_session_store,
    require_csrf,
)
from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.identity.schemas import CurrentUserResponse, LoginRequest, LoginResponse
from app.identity.sessions import SESSION_COOKIE_NAME, SessionData, SessionStore
from app.platform.config import get_settings
from app.platform.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
) -> LoginResponse:
    provider = LocalAuthProvider()
    result = await provider.authenticate(db, username=payload.username, password=payload.password)

    if result is None:
        await record_event(
            db,
            event_type="login_failed",
            username=payload.username,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user = result.user
    session_data = await store.create(
        user_id=user.id,
        username=user.username,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    await record_event(
        db,
        event_type="login",
        user_id=user.id,
        username=user.username,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    await db.commit()

    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_data.session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        csrf_token=session_data.csrf_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_session),
    session_data: SessionData = Depends(get_current_session),
    store: SessionStore = Depends(get_session_store),
) -> None:
    await store.delete(session_data.session_id)
    await record_event(
        db,
        event_type="logout",
        user_id=uuid.UUID(session_data.user_id),
        username=session_data.username,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    await db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CurrentUserResponse:
    permissions = await get_user_permissions(db, user.id)
    return CurrentUserResponse(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        permissions=sorted(permissions),
    )
