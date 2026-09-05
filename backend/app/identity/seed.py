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
    "template:read": "View documentation templates and their versions.",
    "template:write": "Create/edit/publish documentation templates.",
    "model-profile:read": "View model profiles (extraction/document-generation model config).",
    "model-profile:write": "Create/edit model profiles.",
    "processing-profile:read": "View processing profiles (the named end-user presets).",
    "processing-profile:write": "Create/edit/publish processing profiles.",
    # Deprecated aliases kept for backward compatibility with the Phase 1-5
    # seed (the "Template Manager" role already referenced these) — every
    # NEW enforcement point uses the granular codes above instead.
    "profile:write": (
        "Create/edit processing profiles (deprecated alias of processing-profile:write)."
    ),
    "analytics:read": "View analytics/evaluation dashboards.",
    "api:access": "Authenticate as a service account against the API.",
    # Phase 7: retention policy admin management (spec §7's `administration`
    # domain gains a real admin UI over the retention_policies data model
    # that has existed since Phase 2 — no scheduler/enforcement here, see
    # docs/architecture/future-considerations.md's Phase 7 additions).
    "retention:read": "View retention policies.",
    "retention:write": "Create/edit retention policies.",
    # Phase 8 (spec §50/§51): the Evaluation Lab and Model Lifecycle
    # transitions. `analytics:read` (already seeded above, Phase 1) now
    # also gates the technical/quality/correction analytics views and
    # reading evaluation runs/lifecycle history — no separate "read"
    # permission was invented since it already scoped exactly this.
    "evaluation:run": "Run an Evaluation Lab model/prompt comparison.",
    "model-profile:promote": (
        "Transition a model profile's lifecycle status (including rollback)."
    ),
    # Phase 9 (spec §39/§40/§41, roadmap §73): Timeline/external-reference
    # grouping, conversation comparison, and Follow-ups/Tasks. Read access to
    # a conversation's underlying facts/evidence is still gated separately
    # by `fact:read`/`evidence:read` (unchanged) — these new codes gate the
    # longitudinal VIEWS/actions themselves.
    "timeline:read": (
        "View the cross-conversation Timeline/Comparison for a shared external reference."
    ),
    "task:read": "View Follow-ups/Tasks for a conversation.",
    "task:create": "Create a user follow-up/task on a conversation.",
    "task:update": "Update a follow-up/task's status.",
    # Phase 10 (spec §54/§55, roadmap §73): admin management of Service
    # Accounts and Webhooks. Distinct from `api:access` above (Phase 1's
    # pre-existing, still-unused "is this actor allowed to call the API at
    # all" placeholder) -- these gate the ADMIN CRUD over the accounts/
    # webhooks themselves, not API access by a service account (that's
    # authenticated by API key + its own granted scopes, see
    # app.integrations.deps.require_scope, never by a human permission
    # code).
    "service-account:read": "View service accounts (API clients).",
    "service-account:write": "Create, rotate, and revoke service accounts.",
    "webhook:read": "View webhooks and their delivery logs.",
    "webhook:write": "Create, update, and delete webhooks.",
    # Phase 11 (spec §56/§57/§64, roadmap §73): Worker/GPU/Queue metrics,
    # Model Storage view, Backup, and Retention Cleanup. Deliberately
    # narrow and NOT default-granted broadly — backup/retention-cleanup
    # trigger real, operationally significant (retention cleanup:
    # IRREVERSIBLE) actions, so only System Admin gets the *:trigger
    # codes below (see ROLES); Manager/Auditor get read-only visibility.
    "operations:read": "View worker/GPU/queue metrics and model storage usage.",
    "backup:trigger": "Create a real backup (PostgreSQL dump + media archive).",
    "retention-cleanup:trigger": (
        "Run the retention cleanup worker (dry-run or, explicitly, real deletion)."
    ),
    "retention-cleanup:read": "View past retention cleanup runs and their audit trail.",
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
            "retention:read",
            "retention:write",
            "evaluation:run",
            "timeline:read",
            "task:read",
            "task:create",
            "task:update",
            "service-account:read",
            "service-account:write",
            "webhook:read",
            "webhook:write",
            "operations:read",
            "retention-cleanup:read",
        ],
    ),
    "Template Manager": (
        "Manages documentation templates and processing profiles.",
        True,
        [
            "template:read",
            "template:write",
            "model-profile:read",
            "model-profile:write",
            "model-profile:promote",
            "processing-profile:read",
            "processing-profile:write",
            "profile:write",
            "conversation:read",
            "analytics:read",
            "evaluation:run",
        ],
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
            "timeline:read",
            "task:read",
            "task:update",
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
            "processing-profile:read",
            "template:read",
            "timeline:read",
            "task:read",
            "task:create",
            "task:update",
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
            "timeline:read",
            "task:read",
            "operations:read",
            "retention-cleanup:read",
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
