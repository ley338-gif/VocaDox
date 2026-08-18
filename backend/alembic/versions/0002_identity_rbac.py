"""identity, rbac, organizations, audit

Adds the first real domain tables (spec §65: schema starts Phase 1):
users, groups, roles, permissions, and the join tables implementing
permission-based RBAC (user_group_memberships, group_roles,
role_permissions), plus organizations/organization_memberships
(departmental separation, not SaaS multi-tenancy) and audit_events (login
audit trail). Sessions are intentionally NOT a table here — see
ADR-0009 (Valkey-backed session store via the existing CacheBackend
abstraction).

`downgrade()` is fully supported and was verified locally
(`alembic downgrade 0001_baseline` after `upgrade head`) against a real
Postgres 16 instance.

Revision ID: 0002_identity_rbac
Revises: 0001_baseline
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_identity_rbac"
down_revision: str | None = "0001_baseline"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_permissions_code"), "permissions", ["code"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("auth_provider", sa.String(length=32), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False
    )
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_org_membership"),
    )
    op.create_index(
        op.f("ix_organization_memberships_organization_id"),
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_memberships_user_id"),
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_id"),
        "role_permissions",
        ["permission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_permissions_role_id"), "role_permissions", ["role_id"], unique=False
    )

    op.create_table(
        "group_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "role_id", name="uq_group_role"),
    )
    op.create_index(op.f("ix_group_roles_group_id"), "group_roles", ["group_id"], unique=False)
    op.create_index(op.f("ix_group_roles_role_id"), "group_roles", ["role_id"], unique=False)

    op.create_table(
        "user_group_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "group_id", name="uq_user_group_membership"),
    )
    op.create_index(
        op.f("ix_user_group_memberships_group_id"),
        "user_group_memberships",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_group_memberships_user_id"),
        "user_group_memberships",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_group_memberships_user_id"), table_name="user_group_memberships")
    op.drop_index(op.f("ix_user_group_memberships_group_id"), table_name="user_group_memberships")
    op.drop_table("user_group_memberships")

    op.drop_index(op.f("ix_group_roles_role_id"), table_name="group_roles")
    op.drop_index(op.f("ix_group_roles_group_id"), table_name="group_roles")
    op.drop_table("group_roles")

    op.drop_index(op.f("ix_role_permissions_role_id"), table_name="role_permissions")
    op.drop_index(op.f("ix_role_permissions_permission_id"), table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index(
        op.f("ix_organization_memberships_user_id"), table_name="organization_memberships"
    )
    op.drop_index(
        op.f("ix_organization_memberships_organization_id"), table_name="organization_memberships"
    )
    op.drop_table("organization_memberships")

    op.drop_table("groups")

    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")

    op.drop_table("roles")

    op.drop_index(op.f("ix_permissions_code"), table_name="permissions")
    op.drop_table("permissions")

    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
