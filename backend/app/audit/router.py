"""Phase 7 Admin Portal — Audit viewer: `GET /admin/audit-events` lists and
filters the exact `audit_events` rows accumulated since Phase 1 across
every domain. Read-only — this is a viewer, not a change to what gets
audited. Gated by the pre-existing `audit:read` permission (seeded since
Phase 1, granted to System Admin, Manager, and Auditor).

Hard rule (unchanged, verified by inspection of every `record_event` call
site across the codebase): `event_metadata` never contains full
conversation/fact/transcript/document content, passwords, or tokens — only
small structured, non-sensitive context. This router does not change that;
it only reads it back.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditEventListResponse, AuditEventResponse, AuditEventTypesResponse
from app.audit.service import count_events, distinct_event_types, list_events
from app.identity.deps import require_permission
from app.identity.models import User
from app.platform.db.session import get_session

router = APIRouter(prefix="/admin/audit-events", tags=["administration"])

_require_audit_read = require_permission("audit:read")


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events_endpoint(
    _user: User = Depends(_require_audit_read),
    db: AsyncSession = Depends(get_session),
    event_type: str | None = None,
    username: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditEventListResponse:
    events = await list_events(
        db,
        event_type=event_type,
        username=username,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    total = await count_events(
        db, event_type=event_type, username=username, since=since, until=until
    )
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/event-types", response_model=AuditEventTypesResponse)
async def list_event_types_endpoint(
    _user: User = Depends(_require_audit_read),
    db: AsyncSession = Depends(get_session),
) -> AuditEventTypesResponse:
    return AuditEventTypesResponse(event_types=await distinct_event_types(db))
