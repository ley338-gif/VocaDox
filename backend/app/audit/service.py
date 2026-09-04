"""Audit event logging service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    event_metadata: dict[str, object] | None = None,
) -> AuditEvent:
    """Persist one audit event. Never pass raw request bodies, passwords,
    tokens, or conversation content in `event_metadata` — see the module
    docstring on `app.audit.models`.

    Phase 10 (spec §55): this is the single hook point for Webhooks —
    after persisting the event, `app.integrations.service` is given a
    chance to fan it out to any matching, active webhook. No new
    event-detection logic exists anywhere else; a webhook only ever fires
    from an event type that already had a real `record_event(...)` call
    site before this phase (or the one added alongside it,
    `review.required`). The import is local to avoid a module-level
    import cycle risk between the audit and integrations domains."""
    event = AuditEvent(
        event_type=event_type,
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
        event_metadata=event_metadata,
    )
    session.add(event)
    await session.flush()

    from app.integrations.service import maybe_dispatch_webhooks

    await maybe_dispatch_webhooks(
        session, event_type=event_type, event_metadata=event_metadata, audit_event_id=event.id
    )

    return event


# -- Phase 7: Admin Portal — Audit viewer -----------------------------------
#
# Read-only filtering/pagination over the exact rows recorded above (spec
# hard rule, unchanged by this phase: `event_metadata` never carries
# conversation/fact/transcript/document content — this is purely a viewer).


async def list_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if username is not None:
        stmt = stmt.where(AuditEvent.username == username)
    if since is not None:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.created_at <= until)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    stmt = select(func.count()).select_from(AuditEvent)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if username is not None:
        stmt = stmt.where(AuditEvent.username == username)
    if since is not None:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.created_at <= until)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def distinct_event_types(session: AsyncSession) -> list[str]:
    result = await session.execute(select(AuditEvent.event_type).distinct())
    return sorted(row[0] for row in result.all())
