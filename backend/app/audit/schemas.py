"""Pydantic response schemas for the Phase 7 Audit admin viewer."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    user_id: uuid.UUID | None
    username: str | None
    ip_address: str | None
    user_agent: str | None
    event_metadata: dict[str, object] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


class AuditEventTypesResponse(BaseModel):
    event_types: list[str]
