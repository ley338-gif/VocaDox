"""RBAC bootstrap/seed data: the baseline permissions and system roles.

Roles listed here match the product spec's role list exactly: System
Admin, Manager, Template Manager, Reviewer, User, Auditor, API Service
Account. Only the identity/organizations-relevant permissions exist as
real enforcement points in Phase 1; permissions for domains that don't
exist yet (conversation, document, template, ...) are still seeded now so
role definitions are complete and stable — later phases add the
enforcement, not new rows here (spec explicitly asks for "at minimum the
roles/permissions data model and a seed/bootstrap mechanism").

`apply_seed` is idempotent: safe to call on every startup/bootstrap run,
it only inserts rows that don't already exist (matched by `code`/`name`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Permission, Role, RolePermission

# code -> description
PERMISSIONS: dict[str, str] = {
    "system:admin": "Full administrative access to the platform.",
    "user:manage": "Create, update, deactivate users.",
    "group:manage": "Create, update groups and manage memberships/role assignments.",
    "organization:manage": "Create, update organizations and manage memberships.",
    "audit:read": "Read audit log events.",
    "conversation:create": "Start/upload new conversations.",
    "conversation:read": "View conversations.",
    "conversation:delete": "Delete conversations.",
    "document:review": "Review generated documents.",
    "document:approve": "Approve/finalize generated documents.",
    "template:write": "Create/edit documentation templates.",
    "profile:write": "Create/edit processing profiles.",
    "analytics:read": "View analytics/evaluation dashboards.",
    "api:access": "Authenticate as a service account against the API.",
}

# role name -> (description, is_system, [permission codes])
ROLES: dict[str, tuple[str, bool, list[str]]] = {
    "System Admin": (
        "Full platform administration.",
        True,
        list(PERMISSIONS.keys()),
    ),
    "Manager": (
        "Departmental/organizational management.",
        True,
        [
            "user:manage",
            "group:manage",
            "organization:manage",
            "audit:read",
            "conversation:read",
            "document:review",
            "document:approve",
            "analytics:read",
        ],
    ),
    "Template Manager": (
        "Manages documentation templates and processing profiles.",
        True,
        ["template:write", "profile:write", "conversation:read"],
    ),
    "Reviewer": (
        "Reviews and approves generated documents.",
        True,
        ["conversation:read", "document:review", "document:approve"],
    ),
    "User": (
        "Standard clinician/end-user access.",
        True,
        ["conversation:create", "conversation:read"],
    ),
    "Auditor": (
        "Read-only access to audit trails and analytics.",
        True,
        ["audit:read", "analytics:read"],
    ),
    "API Service Account": (
        "Non-interactive service-to-service API access.",
        True,
        ["api:access", "conversation:create", "conversation:read"],
    ),
}


async def apply_seed(session: AsyncSession) -> None:
    """Idempotently ensure all baseline permissions and system roles exist."""
    existing_permissions = {
        p.code: p
        for p in (await session.execute(select(Permission))).scalars().all()
    }
    for code, description in PERMISSIONS.items():
        if code not in existing_permissions:
            permission = Permission(code=code, description=description)
            session.add(permission)
            existing_permissions[code] = permission
    await session.flush()

    existing_roles = {r.name: r for r in (await session.execute(select(Role))).scalars().all()}
    for name, (description, is_system, permission_codes) in ROLES.items():
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, description=description, is_system=is_system)
            session.add(role)
            await session.flush()
            existing_roles[name] = role

        grants_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
        existing_grants = {
            rp.permission_id for rp in (await session.execute(grants_stmt)).scalars().all()
        }
        for code in permission_codes:
            permission = existing_permissions[code]
            if permission.id not in existing_grants:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    await session.flush()
