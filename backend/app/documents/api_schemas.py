"""API request/response schemas for the Phase 5 document/revision/review-
wizard REST surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ComposeRequest(BaseModel):
    pass  # no parameters yet — composition always uses the conversation's current facts


class DocumentRevisionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    revision_number: int
    structured_content: list[dict[str, Any]]
    rendered_text: str
    status: str
    blocking_issue_ids: list[str]
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    template_version_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    current_revision_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    current_revision: DocumentRevisionResponse | None = None

    model_config = {"from_attributes": True}


class ResolveReviewIssueRequest(BaseModel):
    fact_id: uuid.UUID
    action: Literal["confirm", "correct", "remove"]
    corrected_value: dict[str, Any] | None = None


class ApprovalBlockedResponse(BaseModel):
    detail: str
    blocking_issue_ids: list[str]
