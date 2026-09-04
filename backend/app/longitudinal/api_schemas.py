"""Pydantic request/response schemas for the Phase 9 API surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.longitudinal.comparison import ComparisonStatus
from app.longitudinal.models import FollowUpStatus


class TimelineEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    title: str
    conversation_type: str
    status: str
    occurred_at: datetime
    fact_count: int = 0


class TimelineResponse(BaseModel):
    external_reference: str
    conversations: list[TimelineEntry]


class ComparisonItemResponse(BaseModel):
    status: ComparisonStatus
    subject: str
    attribute: str
    conversation_id: uuid.UUID
    conversation_title: str
    current_fact_id: uuid.UUID | None
    current_value: str | None
    prior_fact_id: uuid.UUID | None
    prior_value: str | None
    prior_conversation_id: uuid.UUID | None


class ComparisonResponse(BaseModel):
    external_reference: str
    conversation_count: int
    items: list[ComparisonItemResponse]


class FollowUpTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    source: str
    source_fact_id: uuid.UUID | None
    description: str
    assignee: str | None
    due_date: str | None
    status: str
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CreateTaskRequest(BaseModel):
    description: str = Field(max_length=1024, min_length=1)
    assignee: str | None = Field(default=None, max_length=256)
    due_date: str | None = Field(default=None, max_length=128)


class UpdateTaskRequest(BaseModel):
    status: FollowUpStatus
