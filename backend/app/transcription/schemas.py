"""Pydantic request/response schemas for the transcript + processing REST API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.transcription.models import SegmentReviewStatus


class ProcessRequest(BaseModel):
    diarize: bool = True
    language_hint: str | None = Field(default=None, max_length=16)
    min_speakers: int | None = Field(default=None, ge=1, le=20)
    max_speakers: int | None = Field(default=None, ge=1, le=20)
    reprocess: bool = False


class ProcessingJobResponse(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    progress: int
    attempt: int
    max_attempts: int
    failure_class: str | None
    error_code: str | None
    error_message_safe: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ProcessingStatusResponse(BaseModel):
    conversation_status: str
    jobs: list[ProcessingJobResponse]


class WordSchema(BaseModel):
    text: str
    start_ms: int
    end_ms: int
    confidence: float


class TranscriptSegmentResponse(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    speaker_id: uuid.UUID | None
    sequence: int
    start_ms: int
    end_ms: int
    original_text: str
    corrected_text: str | None
    confidence: float | None
    words: list[WordSchema] | None
    review_status: str
    alignment_quality: str
    review_flag: bool
    review_flag_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    source_media_id: uuid.UUID
    language: str | None
    status: str
    provider: str
    model: str
    model_revision: str | None
    is_active: bool
    error_code: str | None
    error_message_safe: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentCorrectionRequest(BaseModel):
    corrected_text: str | None = Field(default=None, max_length=20000)
    review_status: SegmentReviewStatus | None = None


class SegmentCorrectionResponse(BaseModel):
    id: uuid.UUID
    segment_id: uuid.UUID
    corrected_by_user_id: uuid.UUID | None
    previous_corrected_text: str | None
    new_corrected_text: str
    created_at: datetime

    model_config = {"from_attributes": True}
