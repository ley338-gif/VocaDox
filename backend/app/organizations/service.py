"""Basic CRUD-level domain logic for organizations (Phase 1 foundation
only — org-scoped filtering of other domains' data lands alongside those
domains in later phases)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User
from app.identity.rbac import get_user_permissions
from app.organizations.models import Organization, OrganizationMembership


async def create_organization(
    session: AsyncSession, *, name: str, slug: str, description: str | None = None
) -> Organization:
    org = Organization(name=name, slug=slug, description=description)
    session.add(org)
    await session.flush()
    return org


async def get_organization_by_slug(session: AsyncSession, slug: str) -> Organization | None:
    result = await session.execute(select(Organization).where(Organization.slug == slug))
    return result.scalar_one_or_none()


async def list_organizations(session: AsyncSession) -> list[Organization]:
    result = await session.execute(select(Organization).order_by(Organization.name))
    return list(result.scalars().all())


async def add_member(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMembership:
    membership = OrganizationMembership(organization_id=organization_id, user_id=user_id)
    session.add(membership)
    await session.flush()
    return membership


async def list_members(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[OrganizationMembership]:
    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id
        )
    )
    return list(result.scalars().all())


async def list_organization_ids_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await session.execute(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id
        )
    )
    return [row[0] for row in result.all()]


async def remove_member(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is not None:
        await session.delete(membership)
        await session.flush()


async def user_can_access_organization(
    session: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> bool:
    """True if `user_id` is a member of `organization_id`, or holds
    `system:admin` (the standing bypass every organization-scoped check in
    this codebase already grants that permission). Small, dependency-light
    helper -- deliberately lives here rather than in
    `app.conversations.authz` (whose `assert_organization_member_or_admin`
    delegates to this exact logic) because that module already imports
    `app.organizations.models`; importing the other direction would risk a
    circular import the moment `app.organizations` needs anything from
    `app.conversations`. Used both by that delegation and by the
    `GET /organizations/{id}/member-users` directory endpoint."""
    permissions = await get_user_permissions(session, user_id)
    if "system:admin" in permissions:
        return True
    org_ids = await list_organization_ids_for_user(session, user_id)
    return organization_id in org_ids


async def list_member_users(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[User]:
    """Active users belonging to `organization_id`, sorted by
    `display_name` -- backs the participant-picker directory endpoint
    (`GET /organizations/{id}/member-users`). Deliberately returns full
    `User` rows; the router's `OrganizationMemberUserResponse` schema is
    what narrows this to the minimal, non-admin field set actually
    exposed over HTTP."""
    result = await session.execute(
        select(User)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.display_name)
    )
    return list(result.scalars().all())


async def set_user_organizations(
    session: AsyncSession, *, user_id: uuid.UUID, organization_ids: list[uuid.UUID]
) -> None:
    """Replaces the user's full organization-membership set with exactly
    `organization_ids` (adds missing, removes extras) -- mirrors
    `app.identity.service.set_user_groups` exactly, used by the admin
    "assign organizations" action on `PATCH /admin/users/{id}` rather than
    exposing raw add/remove plumbing to the frontend."""
    current = set(await list_organization_ids_for_user(session, user_id))
    target = set(organization_ids)
    for organization_id in target - current:
        await add_member(session, organization_id=organization_id, user_id=user_id)
    for organization_id in current - target:
        await remove_member(session, organization_id=organization_id, user_id=user_id)
