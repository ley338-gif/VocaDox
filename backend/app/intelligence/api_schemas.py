"""API request/response schemas for the Phase 4 facts/evidence/review-issue
REST surface. Kept separate from app.intelligence.schemas (the LLM
structured-output contracts) — the API never exposes the raw LLM schema
directly, only the persisted ExtractedFact shape."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ExtractRequest(BaseModel):
    pass  # no parameters yet — extraction always uses the active extraction ModelProfile


class ExtractedFactResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    processing_run_id: uuid.UUID | None
    category: str
    fact_type: str
    structured_value: dict[str, Any]
    certainty: str
    confidence: float | None
    status: str
    # Phase 5 Review Wizard fields.
    review_status: str = "pending"
    corrected_structured_value: dict[str, Any] | None = None
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FactEvidenceResponse(BaseModel):
    id: uuid.UUID
    fact_id: uuid.UUID
    transcript_segment_id: uuid.UUID
    evidence_type: str
    created_at: datetime
    # Denormalized for convenience so a frontend can jump to/highlight the
    # source segment without a second round-trip.
    segment_sequence: int | None = None
    segment_start_ms: int | None = None
    segment_end_ms: int | None = None
    segment_text: str | None = None

    model_config = {"from_attributes": True}


class ReviewIssueResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    issue_type: str
    severity: str
    uncertainty_category: str | None
    related_fact_ids: list[str]
    description: str
    status: str
    # Phase 5 Review Wizard resolution fields — null until a human resolves
    # this issue via PATCH /conversations/{id}/review-issues/{issue_id}
    # (app.documents.router).
    resolved_status: str | None = None
    resolved_fact_id: str | None = None
    resolved_by_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
