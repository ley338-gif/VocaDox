"""Conversation/media access control: Permission + Organization Membership +
Conversation's Organization. A user must never reach a Conversation (or its
media) solely by knowing its UUID — see docs/security/threat-model.md,
"cross-organization IDOR".

`system:admin` is the one explicit bypass of the organization-membership
check (platform administrators can reach every organization's data by
design — same posture as Phase 1's admin-gated `/admin` area) but it does
NOT bypass the underlying permission check itself.

**Team scoping (post-GA)**: a Conversation may optionally belong to a
`Group` (reused as "Team" — see app.identity.models.Group's docstring;
no separate Team entity was introduced). `group_id IS NULL` means "no
team assigned, visible to the whole organization" (every pre-existing
conversation, and any created without picking a team). A non-NULL
`group_id` further restricts read access to that Group's members, unless
the caller has `system:admin` or the `conversation:read-cross-team`
permission (granted to the Manager role) — same bypass posture as
`system:admin` already has for organization membership.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.identity.models import User, UserGroupMembership
from app.identity.rbac import get_user_permissions
from app.organizations.models import OrganizationMembership
from app.organizations.service import user_can_access_organization

CROSS_TEAM_PERMISSION = "conversation:read-cross-team"


async def _user_organization_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    result = await session.execute(
        select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == user_id
        )
    )
    return {row[0] for row in result.all()}


async def user_group_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """A user's own team memberships — used both by `authorize_conversation_
    access` below and by the cross-conversation list endpoints
    (`list_conversations`, `list_tasks_for_organizations`) that can't go
    through per-row authorization."""
    result = await session.execute(
        select(UserGroupMembership.group_id).where(UserGroupMembership.user_id == user_id)
    )
    return {row[0] for row in result.all()}


def can_bypass_team_scope(permissions: set[str]) -> bool:
    return "system:admin" in permissions or CROSS_TEAM_PERMISSION in permissions


async def get_conversation_or_404(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.deleted_at.is_(None)
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return conversation


async def authorize_conversation_access(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: uuid.UUID,
    permission_code: str,
) -> Conversation:
    """Load a Conversation and enforce Permission + Organization Membership
    + Conversation's Organization in one place, so every endpoint that
    touches a conversation (or its media/participants/markers/notes) gets
    the same guarantee. Raises 404 for "doesn't exist" AND "exists but you
    have no business knowing that" alike — never distinguishes the two, so
    UUID-guessing can't be used to enumerate other organizations' data."""
    permissions = await get_user_permissions(session, user.id)
    if permission_code not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    conversation = await get_conversation_or_404(session, conversation_id)

    if "system:admin" in permissions:
        return conversation

    org_ids = await _user_organization_ids(session, user.id)
    if conversation.organization_id not in org_ids:
        # Deliberately 404, not 403: do not confirm the conversation exists
        # to a user outside its organization.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    if conversation.group_id is not None and not can_bypass_team_scope(permissions):
        group_ids = await user_group_ids(session, user.id)
        if conversation.group_id not in group_ids:
            # Same 404-not-403 posture as the organization check above —
            # a team boundary must not be distinguishable from "doesn't
            # exist" either.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
            )

    return conversation


async def assert_organization_member_or_admin(
    session: AsyncSession, *, user: User, organization_id: uuid.UUID
) -> None:
    """Delegates to `app.organizations.service.user_can_access_organization`
    (member-or-system:admin) rather than re-implementing the same check —
    see that function's docstring for why the dependency runs this
    direction and not the other."""
    if not await user_can_access_organization(
        session, user_id=user.id, organization_id=organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of the target organization",
        )
