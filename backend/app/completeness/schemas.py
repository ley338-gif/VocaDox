"""API response schema for the template completeness score (post-GA
P1-3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class CategoryCoverageResponse(BaseModel):
    category: str
    title: str
    covered: bool
    fact_count: int

    model_config = {"from_attributes": True}


class SpeakingShareResponse(BaseModel):
    speaker_id: uuid.UUID
    label: str
    speaking_ms: int
    share: float

    model_config = {"from_attributes": True}


class MonologueSpanResponse(BaseModel):
    speaker_id: uuid.UUID
    label: str
    start_ms: int
    end_ms: int
    duration_ms: int

    model_config = {"from_attributes": True}


class CompletenessResponse(BaseModel):
    conversation_id: uuid.UUID
    template_key: str | None
    template_name: str | None
    template_version_id: uuid.UUID | None
    categories: list[CategoryCoverageResponse]
    category_coverage_ratio: float
    decisions_total: int
    decisions_missing_decided_by: int
    tasks_total: int
    tasks_missing_assignee: int
    overall_score: float
    speaking_shares: list[SpeakingShareResponse]
    longest_monologue: MonologueSpanResponse | None
