"""Pydantic request/response schemas for the Phase 8 analytics/evaluation/
model-lifecycle admin API. Every response model here is built from
counts/ids/labels only — none can carry transcript/fact/document content
(verified by test, see tests/analytics/test_privacy.py)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TechnicalAnalyticsResponse(BaseModel):
    window_days: int
    total_jobs: int
    volume_by_day: dict[str, int]
    by_job_type: dict[str, dict[str, Any]]


class QualityMetricsResponse(BaseModel):
    transcript_segments_total: int
    transcript_segments_corrected: int
    transcript_correction_rate: float | None
    fact_review_status_counts: dict[str, int]
    facts_total: int
    fact_corrected_or_removed_rate: float | None
    review_issue_status_counts: dict[str, int]
    review_issue_resolution_counts: dict[str, int]


class CorrectionMetricsResponse(BaseModel):
    fact_corrections_by_category: dict[str, int]
    most_corrected_subjects: list[dict[str, Any]]
    transcript_segment_corrections_total: int


class ModelComparisonRequest(BaseModel):
    model_profile_id_a: uuid.UUID
    model_profile_id_b: uuid.UUID


class PromptComparisonRequest(BaseModel):
    prompt_version_id_a: uuid.UUID
    prompt_version_id_b: uuid.UUID
    model_profile_id: uuid.UUID


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_type: str
    status: str
    fixture_key: str
    subject_a: dict[str, Any]
    subject_b: dict[str, Any]
    result_a: dict[str, Any] | None
    result_b: dict[str, Any] | None
    error_message_safe: str | None
    created_at: datetime
    completed_at: datetime | None


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunResponse]
    total: int
    limit: int
    offset: int


class LifecycleTransitionRequest(BaseModel):
    to_status: str
    is_rollback: bool = False
    checklist: dict[str, bool] | None = None
    note: str | None = None


class LifecycleEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_profile_id: uuid.UUID
    from_status: str | None
    to_status: str
    is_rollback: bool
    checklist: dict[str, Any] | None
    note: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime


class ModelLifecycleResponse(BaseModel):
    model_profile_id: uuid.UUID
    lifecycle_status: str
    events: list[LifecycleEventResponse]
