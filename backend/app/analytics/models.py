"""Phase 8 analytics/evaluation ORM models.

Technical/quality/correction analytics (spec roadmap §73) are computed
on-the-fly from existing Phase 3/4/5 tables (`processing_jobs`,
`transcript_segment_corrections`, `fact_corrections`, `review_issues`) —
no new table for those, see app.analytics.service. The only genuinely new
persisted state this phase introduces is:

- `ModelProfileLifecycleEvent` (spec §51): an append-only audit trail of
  every Model Lifecycle transition (including rollback) — see
  `app.profiles.models.ModelLifecycleStatus` for the status enum, which
  lives on `ModelProfile` itself (extended in Phase 8, not a new table).
- `EvaluationRun` (spec §50): one row per Evaluation Lab comparison run.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class EvaluationRunType(StrEnum):
    MODEL_COMPARISON = "model_comparison"
    PROMPT_COMPARISON = "prompt_comparison"


class EvaluationRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelProfileLifecycleEvent(Base):
    """One row per lifecycle transition on a `ModelProfile` — never
    updated once written, mirroring `FactCorrection`/
    `TranscriptSegmentCorrection`'s "one row per event" pattern. This is
    what makes rollback safe: the full history of every status a profile
    was ever in (and who moved it, and why) survives a rollback rather
    than being overwritten."""

    __tablename__ = "model_profile_lifecycle_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("model_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_rollback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Spec §51's model-update checklist (License Check / Compatibility
    # Check / Benchmark / Security Review / Admin Approval) — recorded as
    # a small JSON bag of booleans/labels the admin asserted true when
    # making the transition. This is a DOCUMENTED admin attestation, not
    # something this codebase can verify automatically (see
    # app.analytics.service's module docstring).
    checklist: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvaluationRun(Base):
    """One Evaluation Lab comparison (spec §50): two "subjects" (either two
    `ModelProfile`s or two `PromptVersion`s) run against the same synthetic
    fixture (app.analytics.fixtures), with real measured results for each.

    `subject_a`/`subject_b` store only ids/names/config (never transcript
    content) describing what was compared; `result_a`/`result_b` store
    only the counts/booleans `EvalResult.as_public_dict()` produces — see
    app.analytics.eval_engine. A run that fails outright (e.g. the
    provider was unreachable) is stored as `status=failed` with
    `error_message_safe` set rather than silently discarded, so a
    NOT-VERIFIED comparison is visible, not hidden."""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EvaluationRunStatus.RUNNING.value, index=True
    )
    fixture_key: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_a: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    subject_b: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_a: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_b: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
