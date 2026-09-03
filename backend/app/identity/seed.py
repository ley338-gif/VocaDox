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
    "conversation:update": "Edit conversation metadata.",
    "conversation:delete": "Delete conversations.",
    "conversation:record": "Record audio via the browser capture workflow.",
    "conversation:upload": "Upload an existing audio file as conversation source media.",
    "conversation:manage-participants": "Add/edit/remove conversation participants.",
    "conversation:manage-notes": "Add/edit/remove conversation notes.",
    "conversation:manage-markers": "Add/edit/remove conversation recording markers.",
    "media:read": "View/play conversation media.",
    "media:upload": "Upload media onto an existing conversation.",
    "media:delete": "Delete conversation media.",
    "transcript:read": "View a conversation's transcript.",
    "transcript:process": "Trigger speech-to-text/diarization processing for a conversation.",
    "transcript:correct": "Correct transcript segment text / set segment review status.",
    "speaker:read": "View detected speakers for a conversation.",
    "speaker:assign": "Assign/unassign a detected speaker to a participant or display label.",
    "processing:read": "View processing job/run status for a conversation.",
    "processing:retry": "Retry a failed processing job; cancel a queued one.",
    "provider:read": "View admin speech/diarization provider status.",
    "provider:test": "Trigger an admin-initiated provider health check.",
    "fact:read": "View extracted facts for a conversation.",
    "fact:extract": "Trigger LLM fact extraction for a conversation's transcript.",
    "evidence:read": "View the evidence (transcript segments) linked to an extracted fact.",
    "review-issue:read": "View review issues (uncertainty/contradiction flags) for a conversation.",
    "review-issue:resolve": (
        "Resolve a review issue via the Review Wizard (confirm/correct/remove)."
    ),
    "document:review": "Review generated documents.",
    "document:read": "View a conversation's composed document and revision history.",
    "document:edit": "Compose a document and apply fact corrections during review.",
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
            "conversation:update",
            "conversation:delete",
            "conversation:manage-participants",
            "conversation:manage-notes",
            "conversation:manage-markers",
            "media:read",
            "media:delete",
            "document:review",
            "document:approve",
            "analytics:read",
            "transcript:read",
            "transcript:process",
            "transcript:correct",
            "speaker:read",
            "speaker:assign",
            "processing:read",
            "processing:retry",
            "fact:read",
            "fact:extract",
            "evidence:read",
            "review-issue:read",
            "review-issue:resolve",
            "document:read",
            "document:edit",
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
        [
            "conversation:read",
            "media:read",
            "document:review",
            "document:approve",
            "transcript:read",
            "speaker:read",
            "processing:read",
            "fact:read",
            "evidence:read",
            "review-issue:read",
            "review-issue:resolve",
            "document:read",
            "document:edit",
        ],
    ),
    "User": (
        "Standard clinician/end-user access.",
        True,
        [
            "conversation:create",
            "conversation:read",
            "conversation:update",
            "conversation:record",
            "conversation:upload",
            "conversation:manage-participants",
            "conversation:manage-notes",
            "conversation:manage-markers",
            "conversation:delete",
            "media:read",
            "media:upload",
            "media:delete",
            "transcript:read",
            "transcript:process",
            "transcript:correct",
            "speaker:read",
            "speaker:assign",
            "processing:read",
            "processing:retry",
            "fact:read",
            "fact:extract",
            "evidence:read",
            "review-issue:read",
            "review-issue:resolve",
            "document:read",
            "document:edit",
        ],
    ),
    "Auditor": (
        "Read-only access to audit trails and analytics.",
        True,
        [
            "audit:read",
            "analytics:read",
            "transcript:read",
            "speaker:read",
            "processing:read",
            "fact:read",
            "evidence:read",
            "review-issue:read",
            "document:read",
        ],
    ),
    "API Service Account": (
        "Non-interactive service-to-service API access.",
        True,
        [
            "api:access",
            "conversation:create",
            "conversation:read",
            "conversation:upload",
            "media:read",
            "media:upload",
        ],
    ),
}


async def apply_seed(session: AsyncSession) -> None:
    """Idempotently ensure all baseline permissions and system roles exist."""
    existing_permissions = {
        p.code: p for p in (await session.execute(select(Permission))).scalars().all()
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


async def _reseed_cli() -> int:  # pragma: no cover - trivial CLI wrapper
    """`python -m app.identity.seed` — idempotently apply the current
    PERMISSIONS/ROLES tables against the configured database, without
    creating any user. This is the Phase-1 -> Phase-2 upgrade path for
    picking up the new conversation:*/media:* permission codes on an
    existing installation: `alembic upgrade head` (schema) followed by this
    (RBAC seed data) — no manual SQL, no re-running bootstrap_admin."""
    from app.platform.db import model_registry  # noqa: F401 - registers all domain models
    from app.platform.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_seed(session)
        await session.commit()
    print("RBAC seed applied (permissions/roles created or already up to date).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_reseed_cli()))
