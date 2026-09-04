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
    require_permission,
)
from app.identity.models import Group, User
from app.identity.rbac import get_user_permissions
from app.identity.schemas import (
    CsrfTokenResponse,
    CurrentUserResponse,
    GroupCreateRequest,
    GroupDetailResponse,
    GroupResponse,
    GroupUpdateRequest,
    LoginRequest,
    LoginResponse,
    RoleResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserSummaryResponse,
    UserUpdateRequest,
)
from app.identity.service import (
    create_group,
    create_local_user,
    get_group,
    get_user,
    get_user_by_username,
    list_group_ids_for_user,
    list_groups,
    list_members_of_group,
    list_role_ids_for_group,
    list_roles,
    list_users,
    set_group_roles,
    set_user_groups,
    update_group,
    update_user,
)
from app.identity.sessions import SESSION_COOKIE_NAME, SessionData, SessionStore
from app.platform.config import get_settings
from app.platform.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])
admin_users_router = APIRouter(prefix="/admin/users", tags=["administration"])
admin_groups_router = APIRouter(prefix="/admin/groups", tags=["administration"])
admin_roles_router = APIRouter(prefix="/admin/roles", tags=["administration"])

_require_user_manage = require_permission("user:manage")
_require_group_manage = require_permission("group:manage")


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
    response_model=None,
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


@router.get("/csrf", response_model=CsrfTokenResponse)
async def csrf(
    session_data: SessionData = Depends(get_current_session),
) -> CsrfTokenResponse:
    """Recover the current session's CSRF token after a full page reload
    wiped the frontend's in-memory copy (session cookie itself is
    httponly and unaffected by reload). Safe as a plain GET: it only
    re-reads a token already bound to the caller's own authenticated
    session, never mints a new one or reveals another user's token."""
    return CsrfTokenResponse(csrf_token=session_data.csrf_token)


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


# -- Phase 7: Admin Portal — Users -------------------------------------------


@admin_users_router.get("", response_model=list[UserSummaryResponse])
async def list_users_endpoint(
    _user: User = Depends(_require_user_manage),
    db: AsyncSession = Depends(get_session),
) -> list[UserSummaryResponse]:
    return [UserSummaryResponse.model_validate(u) for u in await list_users(db)]


@admin_users_router.post(
    "", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_user_endpoint(
    payload: UserCreateRequest,
    actor: User = Depends(_require_user_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> UserDetailResponse:
    if await get_user_by_username(db, payload.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"username {payload.username!r} exists"
        )
    new_user = await create_local_user(
        db,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        email=payload.email,
    )
    if payload.group_ids:
        await set_user_groups(db, user_id=new_user.id, group_ids=payload.group_ids)
    await record_event(
        db,
        event_type="user.created",
        user_id=actor.id,
        username=actor.username,
        event_metadata={"created_user_id": str(new_user.id)},
    )
    await db.commit()
    await db.refresh(new_user)
    group_ids = await list_group_ids_for_user(db, new_user.id)
    return UserDetailResponse(
        id=new_user.id,
        username=new_user.username,
        display_name=new_user.display_name,
        email=new_user.email,
        auth_provider=new_user.auth_provider,
        is_active=new_user.is_active,
        group_ids=group_ids,
    )


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    found = await get_user(db, user_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return found


@admin_users_router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_endpoint(
    user_id: uuid.UUID,
    _user: User = Depends(_require_user_manage),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    found = await _get_user_or_404(db, user_id)
    group_ids = await list_group_ids_for_user(db, found.id)
    return UserDetailResponse(
        id=found.id,
        username=found.username,
        display_name=found.display_name,
        email=found.email,
        auth_provider=found.auth_provider,
        is_active=found.is_active,
        group_ids=group_ids,
    )


@admin_users_router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    actor: User = Depends(_require_user_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> UserDetailResponse:
    """Also the deactivation endpoint (`is_active: false`) — spec: admin UI
    to "list/view/create/deactivate users" never hard-deletes a user row."""
    found = await _get_user_or_404(db, user_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"group_ids"})
    found = await update_user(db, found, **changes)
    if payload.group_ids is not None:
        await set_user_groups(db, user_id=found.id, group_ids=payload.group_ids)
    await record_event(
        db,
        event_type="user.updated",
        user_id=actor.id,
        username=actor.username,
        event_metadata={"updated_user_id": str(found.id), "fields": sorted(changes.keys())},
    )
    await db.commit()
    await db.refresh(found)
    group_ids = await list_group_ids_for_user(db, found.id)
    return UserDetailResponse(
        id=found.id,
        username=found.username,
        display_name=found.display_name,
        email=found.email,
        auth_provider=found.auth_provider,
        is_active=found.is_active,
        group_ids=group_ids,
    )


# -- Phase 7: Admin Portal — Groups -------------------------------------------


async def _group_detail(db: AsyncSession, group: Group) -> GroupDetailResponse:
    role_ids = await list_role_ids_for_group(db, group.id)
    members = await list_members_of_group(db, group.id)
    return GroupDetailResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        organization_id=group.organization_id,
        role_ids=role_ids,
        member_ids=[m.id for m in members],
    )


@admin_groups_router.get("", response_model=list[GroupResponse])
async def list_groups_endpoint(
    _user: User = Depends(_require_group_manage),
    db: AsyncSession = Depends(get_session),
) -> list[GroupResponse]:
    return [GroupResponse.model_validate(g) for g in await list_groups(db)]


@admin_groups_router.post(
    "", response_model=GroupDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_group_endpoint(
    payload: GroupCreateRequest,
    user: User = Depends(_require_group_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> GroupDetailResponse:
    group = await create_group(
        db,
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id,
    )
    if payload.role_ids:
        await set_group_roles(db, group_id=group.id, role_ids=payload.role_ids)
    await db.commit()
    await db.refresh(group)
    return await _group_detail(db, group)


async def _get_group_or_404(db: AsyncSession, group_id: uuid.UUID) -> Group:
    group = await get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    return group


@admin_groups_router.get("/{group_id}", response_model=GroupDetailResponse)
async def get_group_endpoint(
    group_id: uuid.UUID,
    _user: User = Depends(_require_group_manage),
    db: AsyncSession = Depends(get_session),
) -> GroupDetailResponse:
    group = await _get_group_or_404(db, group_id)
    return await _group_detail(db, group)


@admin_groups_router.patch("/{group_id}", response_model=GroupDetailResponse)
async def update_group_endpoint(
    group_id: uuid.UUID,
    payload: GroupUpdateRequest,
    user: User = Depends(_require_group_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> GroupDetailResponse:
    group = await _get_group_or_404(db, group_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"role_ids"})
    group = await update_group(db, group, **changes)
    if payload.role_ids is not None:
        await set_group_roles(db, group_id=group.id, role_ids=payload.role_ids)
    await db.commit()
    await db.refresh(group)
    return await _group_detail(db, group)


# -- Phase 7: Admin Portal — Roles (read-only; role definitions are
# seeded/bootstrap-managed, see app.identity.seed) --------------------------


@admin_roles_router.get("", response_model=list[RoleResponse])
async def list_roles_endpoint(
    _user: User = Depends(_require_group_manage),
    db: AsyncSession = Depends(get_session),
) -> list[RoleResponse]:
    return [RoleResponse.model_validate(r) for r in await list_roles(db)]
