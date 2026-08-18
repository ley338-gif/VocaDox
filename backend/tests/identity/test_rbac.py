"""Tests for genuine permission-based RBAC resolution (User -> Group ->
Role -> Permission), not role-name string comparisons."""

from __future__ import annotations

from app.identity.models import (
    Group,
    GroupRole,
    Permission,
    Role,
    RolePermission,
    User,
    UserGroupMembership,
)
from app.identity.rbac import get_user_permissions, user_has_permission
from app.identity.service import add_user_to_group
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_user(db_session: AsyncSession, username: str = "alice") -> User:
    user = User(username=username, display_name=username, is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


async def test_user_with_no_groups_has_no_permissions(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    permissions = await get_user_permissions(db_session, user.id)
    assert permissions == set()


async def test_permission_resolved_through_group_and_role(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    permission = Permission(code="conversation:create", description="")
    role = Role(name="User", description="", is_system=True)
    group = Group(name="Clinicians")
    db_session.add_all([permission, role, group])
    await db_session.flush()

    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.add(GroupRole(group_id=group.id, role_id=role.id))
    await add_user_to_group(db_session, user_id=user.id, group_id=group.id)
    await db_session.flush()

    permissions = await get_user_permissions(db_session, user.id)
    assert permissions == {"conversation:create"}
    assert await user_has_permission(db_session, user.id, "conversation:create") is True
    assert await user_has_permission(db_session, user.id, "system:admin") is False


async def test_permissions_are_union_across_multiple_groups(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)

    perm_a = Permission(code="template:write", description="")
    perm_b = Permission(code="audit:read", description="")
    role_a = Role(name="Template Manager", is_system=True)
    role_b = Role(name="Auditor", is_system=True)
    group_a = Group(name="Templating")
    group_b = Group(name="Compliance")
    db_session.add_all([perm_a, perm_b, role_a, role_b, group_a, group_b])
    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(role_id=role_a.id, permission_id=perm_a.id),
            RolePermission(role_id=role_b.id, permission_id=perm_b.id),
            GroupRole(group_id=group_a.id, role_id=role_a.id),
            GroupRole(group_id=group_b.id, role_id=role_b.id),
        ]
    )
    await add_user_to_group(db_session, user_id=user.id, group_id=group_a.id)
    await add_user_to_group(db_session, user_id=user.id, group_id=group_b.id)
    await db_session.flush()

    permissions = await get_user_permissions(db_session, user.id)
    assert permissions == {"template:write", "audit:read"}


async def test_removing_group_membership_removes_permission(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    permission = Permission(code="system:admin", description="")
    role = Role(name="System Admin", is_system=True)
    group = Group(name="Administrators")
    db_session.add_all([permission, role, group])
    await db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.add(GroupRole(group_id=group.id, role_id=role.id))
    await add_user_to_group(db_session, user_id=user.id, group_id=group.id)
    await db_session.flush()

    assert await user_has_permission(db_session, user.id, "system:admin") is True

    # add_user_to_group returns None on the idempotent no-op path; fetch
    # the actual membership row to delete it.
    result = await db_session.execute(
        select(UserGroupMembership).where(UserGroupMembership.user_id == user.id)
    )
    membership = result.scalar_one()
    await db_session.delete(membership)
    await db_session.flush()

    assert await user_has_permission(db_session, user.id, "system:admin") is False
