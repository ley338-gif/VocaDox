"""Generalized processing provenance/orchestration models (Phase 3).

`ProcessingRun` is the provenance record for one execution of one
processing stage (NORMALIZATION / SPEECH_TO_TEXT / DIARIZATION /
ALIGNMENT) against one SourceMedia — "what actually produced this data,
with what provider/model/config, when". `ProcessingJob` is the
orchestration record — "what work is queued/running/done" — consumed by
worker processes via the existing `QueueBackend` abstraction (never
Valkey directly; see app.platform.valkey).

A `ProcessingJob` may or may not result in a `ProcessingRun` (e.g. a job
that fails before actually invoking a provider has no run); a
`ProcessingRun` always corresponds to exactly one job's successful or
attempted execution. They are linked by `processing_run_id` on the job,
set once the run row exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class RunType(StrEnum):
    NORMALIZATION = "normalization"
    SPEECH_TO_TEXT = "speech_to_text"
    DIARIZATION = "diarization"
    ALIGNMENT = "alignment"


class JobType(StrEnum):
    NORMALIZE = "normalize"
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    ALIGN = "align"
    # No LLM job types exist yet (Phase 4+). Documented here only so the
    # enum's eventual growth path is visible in one place.


class ProcessingStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FailureClass(StrEnum):
    """How a failed ProcessingJob should be treated for retry purposes.
    See app.processing.retry for the policy table keyed on this enum."""

    TRANSIENT = "transient"  # worker hiccup, network blip -> retry
    PERMANENT = "permanent"  # e.g. corrupt/unsupported audio -> do not retry
    RESOURCE = "resource"  # OOM/VRAM exhaustion -> retry later, not immediately
    INPUT_INVALID = "input_invalid"  # bad input data -> do not retry
    MODEL_UNAVAILABLE = "model_unavailable"  # model not installed -> do not auto-retry


class ProcessingRun(Base):
    """Provenance record for one execution of one processing stage.

    `configuration_snapshot` captures enough to explain the result later
    without depending on today's global config (language, device,
    compute_type, beam_size, vad_enabled, speaker_count_hint,
    normalization_profile, ...). Never contains secrets (e.g. no HF
    tokens).
    """

    __tablename__ = "processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_media_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RunStatus.RUNNING.value
    )

    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)

    configuration_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    application_version: Mapped[str] = mapped_column(String(32), nullable=False)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessingJob(Base):
    """Orchestration record for one unit of async processing work, executed
    by a worker process via QueueBackend. Never executed inline in an HTTP
    request handler.
    """

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_media_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProcessingStatus.QUEUED.value, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    failure_class: Mapped[str | None] = mapped_column(String(32), nullable=True)

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Lease/heartbeat for worker-crash recovery: a job RUNNING with a
    # heartbeat older than the lease timeout is considered abandoned and
    # eligible for requeue. See app.processing.service.reclaim_stale_jobs.
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_runs.id", ondelete="SET NULL"), nullable=True
    )
    # Free-form config the job was queued with (model/profile hint, source
    # of the chain trigger) — kept small, non-secret.
    job_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
