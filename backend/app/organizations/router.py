"""Minimal read-only organizations endpoint: `GET /organizations` returns
the organizations the current user belongs to (or every organization for
`system:admin`). Added in Phase 2 because the conversation-creation flow
needs to let a user pick which of *their* organizations a new Conversation
belongs to — Phase 1 only shipped the organizations data model, no API.
Full organization management (create/update/membership admin) remains out
of scope; that is the Phase 7 admin area's job.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.deps import get_current_user, require_csrf, require_permission
from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.organizations.models import Organization, OrganizationMembership
from app.organizations.schemas import (
    AddMemberRequest,
    OrganizationCreateRequest,
    OrganizationMembershipResponse,
    OrganizationResponse,
)
from app.organizations.service import (
    add_member,
    create_organization,
    get_organization_by_slug,
    list_members,
)
from app.platform.db.session import get_session

router = APIRouter(prefix="/organizations", tags=["organizations"])

_require_org_manage = require_permission("organization:manage")


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[OrganizationResponse]:
    permissions = await get_user_permissions(db, user.id)
    if "system:admin" in permissions:
        result = await db.execute(select(Organization).order_by(Organization.name))
    else:
        result = await db.execute(
            select(Organization)
            .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
            .where(OrganizationMembership.user_id == user.id)
            .order_by(Organization.name)
        )
    return [OrganizationResponse.model_validate(org) for org in result.scalars().all()]


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_endpoint(
    payload: OrganizationCreateRequest,
    _user: User = Depends(_require_org_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> OrganizationResponse:
    """Phase 7's admin org-management surface. Closes the pre-existing gap
    flagged in the Phase 5/6 validation reports: organization creation
    previously had no HTTP endpoint (only `app.organizations.service
    .create_organization`, callable from a one-off script/tests)."""
    if await get_organization_by_slug(db, payload.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"organization slug {payload.slug!r} exists",
        )
    org = await create_organization(
        db, name=payload.name, slug=payload.slug, description=payload.description
    )
    await db.commit()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org)


@router.get("/{organization_id}/members", response_model=list[OrganizationMembershipResponse])
async def list_organization_members_endpoint(
    organization_id: uuid.UUID,
    _user: User = Depends(_require_org_manage),
    db: AsyncSession = Depends(get_session),
) -> list[OrganizationMembershipResponse]:
    memberships = await list_members(db, organization_id=organization_id)
    return [OrganizationMembershipResponse.model_validate(m) for m in memberships]


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member_endpoint(
    organization_id: uuid.UUID,
    payload: AddMemberRequest,
    _user: User = Depends(_require_org_manage),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> OrganizationMembershipResponse:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    target_user = await db.get(User, payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    existing = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == payload.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already a member")
    membership = await add_member(db, organization_id=organization_id, user_id=payload.user_id)
    await db.commit()
    await db.refresh(membership)
    return OrganizationMembershipResponse.model_validate(membership)
