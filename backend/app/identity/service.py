"""User/group/role domain logic shared by the bootstrap CLI and (in later
phases) the admin API."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import (
    AuthProviderType,
    Group,
    GroupRole,
    Role,
    User,
    UserGroupMembership,
)
from app.identity.passwords import hash_password


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_local_user(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
    email: str | None = None,
) -> User:
    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=hash_password(password),
        auth_provider=AuthProviderType.LOCAL.value,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def get_role_by_name(session: AsyncSession, name: str) -> Role | None:
    result = await session.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def get_or_create_group(
    session: AsyncSession, *, name: str, description: str | None = None
) -> Group:
    result = await session.execute(select(Group).where(Group.name == name))
    group = result.scalar_one_or_none()
    if group is None:
        group = Group(name=name, description=description)
        session.add(group)
        await session.flush()
    return group


async def assign_role_to_group(
    session: AsyncSession, *, group_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(GroupRole).where(GroupRole.group_id == group_id, GroupRole.role_id == role_id)
    )
    if result.scalar_one_or_none() is None:
        session.add(GroupRole(group_id=group_id, role_id=role_id))
        await session.flush()


async def add_user_to_group(
    session: AsyncSession, *, user_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.user_id == user_id, UserGroupMembership.group_id == group_id
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(UserGroupMembership(user_id=user_id, group_id=group_id))
        await session.flush()


async def any_user_has_role(session: AsyncSession, role_name: str) -> bool:
    """True if at least one user is (transitively, via a group) assigned
    `role_name`. Used by the bootstrap CLI to refuse re-running once a
    System Admin already exists."""
    role = await get_role_by_name(session, role_name)
    if role is None:
        return False
    stmt = (
        select(UserGroupMembership.user_id)
        .join(GroupRole, GroupRole.group_id == UserGroupMembership.group_id)
        .where(GroupRole.role_id == role.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first() is not None


# -- Phase 7: Admin Portal (Users/Groups) surface ---------------------------
#
# Everything below is genuine CRUD/read logic over the exact Phase 1 RBAC
# model above — no parallel permission system, no new tables. Router-level
# permission gating (`user:manage`/`group:manage`, seeded since Phase 1)
# lives in app.identity.router.


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.username))
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def update_user(
    session: AsyncSession,
    user: User,
    *,
    display_name: str | None = None,
    email: str | None = None,
    is_active: bool | None = None,
) -> User:
    if display_name is not None:
        user.display_name = display_name
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
    await session.flush()
    return user


async def list_group_ids_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(UserGroupMembership.group_id).where(UserGroupMembership.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def remove_user_from_group(
    session: AsyncSession, *, user_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.user_id == user_id, UserGroupMembership.group_id == group_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is not None:
        await session.delete(membership)
        await session.flush()


async def set_user_groups(
    session: AsyncSession, *, user_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> None:
    """Replaces the user's full group-membership set with exactly
    `group_ids` (adds missing, removes extras) — used by the admin
    "assign groups" action rather than exposing raw add/remove plumbing to
    the frontend."""
    current = set(await list_group_ids_for_user(session, user_id))
    target = set(group_ids)
    for group_id in target - current:
        await add_user_to_group(session, user_id=user_id, group_id=group_id)
    for group_id in current - target:
        await remove_user_from_group(session, user_id=user_id, group_id=group_id)


async def list_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(select(Group).order_by(Group.name))
    return list(result.scalars().all())


async def get_group(session: AsyncSession, group_id: uuid.UUID) -> Group | None:
    return await session.get(Group, group_id)


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    organization_id: uuid.UUID | None = None,
) -> Group:
    group = Group(name=name, description=description, organization_id=organization_id)
    session.add(group)
    await session.flush()
    return group


async def update_group(
    session: AsyncSession,
    group: Group,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Group:
    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
    await session.flush()
    return group


async def list_role_ids_for_group(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(
        select(GroupRole.role_id).where(GroupRole.group_id == group_id)
    )
    return [row[0] for row in result.all()]


async def remove_role_from_group(
    session: AsyncSession, *, group_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(GroupRole).where(GroupRole.group_id == group_id, GroupRole.role_id == role_id)
    )
    link = result.scalar_one_or_none()
    if link is not None:
        await session.delete(link)
        await session.flush()


async def set_group_roles(
    session: AsyncSession, *, group_id: uuid.UUID, role_ids: list[uuid.UUID]
) -> None:
    """Replaces the group's full role-grant set with exactly `role_ids`."""
    current = set(await list_role_ids_for_group(session, group_id))
    target = set(role_ids)
    for role_id in target - current:
        await assign_role_to_group(session, group_id=group_id, role_id=role_id)
    for role_id in current - target:
        await remove_role_from_group(session, group_id=group_id, role_id=role_id)


async def list_members_of_group(session: AsyncSession, group_id: uuid.UUID) -> list[User]:
    stmt = (
        select(User)
        .join(UserGroupMembership, UserGroupMembership.user_id == User.id)
        .where(UserGroupMembership.group_id == group_id)
        .order_by(User.username)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_roles(session: AsyncSession) -> list[Role]:
    result = await session.execute(select(Role).order_by(Role.name))
    return list(result.scalars().all())
