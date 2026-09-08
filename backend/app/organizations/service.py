"""Basic CRUD-level domain logic for organizations (Phase 1 foundation
only — org-scoped filtering of other domains' data lands alongside those
domains in later phases)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
