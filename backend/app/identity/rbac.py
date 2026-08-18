"""Permission resolution: genuine permission-based RBAC.

Authorization decisions throughout the codebase must check for a specific
permission code (e.g. `conversation:create`, `system:admin`) via
`get_user_permissions` / `user_has_permission` — never compare a role name
or group name directly. This module is the only place that walks the
User -> Group -> Role -> Permission chain.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import (
    GroupRole,
    Permission,
    RolePermission,
    UserGroupMembership,
)


async def get_user_permissions(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Union of every permission code reachable from `user_id` through all
    of their group memberships and each group's assigned roles."""
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(GroupRole, GroupRole.role_id == RolePermission.role_id)
        .join(UserGroupMembership, UserGroupMembership.group_id == GroupRole.group_id)
        .where(UserGroupMembership.user_id == user_id)
        .distinct()
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


async def user_has_permission(session: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    permissions = await get_user_permissions(session, user_id)
    return code in permissions
