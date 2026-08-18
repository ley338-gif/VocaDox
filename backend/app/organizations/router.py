"""Minimal read-only organizations endpoint: `GET /organizations` returns
the organizations the current user belongs to (or every organization for
`system:admin`). Added in Phase 2 because the conversation-creation flow
needs to let a user pick which of *their* organizations a new Conversation
belongs to — Phase 1 only shipped the organizations data model, no API.
Full organization management (create/update/membership admin) remains out
of scope; that is the Phase 7 admin area's job.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.deps import get_current_user
from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.organizations.models import Organization, OrganizationMembership
from app.organizations.schemas import OrganizationResponse
from app.platform.db.session import get_session

router = APIRouter(prefix="/organizations", tags=["organizations"])


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
