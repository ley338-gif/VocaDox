"""SQLAlchemy ORM models for the identity domain: users, groups, roles,
permissions, and the join tables that connect them into permission-based
RBAC (spec: authorization must be permission-based, e.g. `conversation:create`,
never a scattered `if role == "admin"` check).

Resolution chain: User --(membership)--> Group --(assignment)--> Role
--(grant)--> Permission. A user's effective permission set is the union of
every permission reachable through every group they belong to (see
`app.identity.rbac.get_user_permissions`).

Sessions are intentionally NOT modeled here — see ADR-0009
(docs/architecture/adr/0009-session-storage.md) for why sessions live in
Valkey via the existing `CacheBackend` abstraction instead of a DB table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.session import Base


class AuthProviderType(StrEnum):
    """Supported identity providers (spec: multi-provider architecture).

    Only LOCAL is actually implemented in Phase 1. OIDC / LDAP_AD /
    REVERSE_PROXY exist here so the `users.auth_provider` column and the
    `AuthProvider` interface (see `app.identity.auth_providers`) never need
    to change shape when those are implemented in a later phase.
    """

    LOCAL = "local"
    OIDC = "oidc"
    LDAP_AD = "ldap_ad"
    REVERSE_PROXY = "reverse_proxy"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)

    # Nullable: users authenticated via a future external provider (OIDC /
    # LDAP_AD / REVERSE_PROXY) never have a local password hash.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auth_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AuthProviderType.LOCAL.value
    )
    # Subject identifier from an external IdP (OIDC `sub`, LDAP DN, ...).
    # Unused for LOCAL users.
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    group_memberships: Mapped[list[UserGroupMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Group(Base):
    """A group is the unit of role assignment (and, per the product spec,
    the on-prem organizational/departmental grouping mechanism — e.g.
    "General Medicine", "Psychotherapy", "Administration")."""

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Nullable: not every group is scoped to an organization (e.g. a
    # system-wide "Administrators" group used for bootstrap).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    member_links: Mapped[list[UserGroupMembership]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    role_links: Mapped[list[GroupRole]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Role(Base):
    """A named bundle of permissions. Seeded roles (spec): System Admin,
    Manager, Template Manager, Reviewer, User, Auditor, API Service
    Account — see `app.identity.seed`."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # System roles are seeded/bootstrap-managed and should not be deleted
    # via ordinary admin UI actions in later phases.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    permission_links: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class Permission(Base):
    """A single fine-grained permission, e.g. `conversation:create`,
    `document:approve`, `template:write`, `system:admin`."""

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class UserGroupMembership(Base):
    __tablename__ = "user_group_memberships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="group_memberships")
    group: Mapped[Group] = relationship(back_populates="member_links")

    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group_membership"),)


class GroupRole(Base):
    """Role assignment: which roles a group grants to its members."""

    __tablename__ = "group_roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    group: Mapped[Group] = relationship(back_populates="role_links")
    role: Mapped[Role] = relationship()

    __table_args__ = (UniqueConstraint("group_id", "role_id", name="uq_group_role"),)


class RolePermission(Base):
    """Grant: which permissions a role carries."""

    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[Role] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship()

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)
