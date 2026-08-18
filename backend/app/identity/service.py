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
