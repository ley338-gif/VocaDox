"""Audit event logging service."""

from __future__ import annotations

import uuid

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
    docstring on `app.audit.models`."""
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
    return event
