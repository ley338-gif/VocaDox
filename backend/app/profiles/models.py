"""`ModelProfile` (spec §17/§18) started as a Phase 4 minimal foundation
(single "extraction" purpose, DB row instead of a hardcoded string) and is
now, as of Phase 6, a real admin-manageable, versioned entity — see
`ModelProfileVersion` below and `app.profiles.router`.

`ProcessingProfile`/`ProcessingProfileVersion` (spec §19) are the Phase 6
addition proper: the named, user-friendly preset ("General", "Meeting", …)
that bundles a Speech provider config + Diarization provider config +
Extraction Model (a `ModelProfile`) + (reserved) Document Model + Template
+ Prompt Version + Language + Retention Policy into one thing an end user
picks by name — "User sieht verständliche Namen. Admin verwaltet
technische Details" (spec). Speech/Diarization remain file/env-based
`Settings`-driven configuration rather than a full `SpeechProfile`/
`DiarizationProfile` DB entity (that table is still Phase 7 — see
docs/architecture/model-management-foundation.md); a `ProcessingProfileVersion`
stores a small provider-name/config JSON for each rather than a real FK,
which is an honest, documented scope boundary, not an oversight.

Exactly one enabled `ModelProfile` per `purpose` is expected to exist at a
time (enforced by app.profiles.seed's idempotent bootstrap for the
`extraction` purpose, not a DB constraint); the extraction worker resolves
its model via `app.profiles.service.get_active_profile(purpose="extraction")`
unless a `ProcessingProfileVersion` names a specific one (see
app.profiles.resolver for the full SYSTEM DEFAULT -> PROCESSING PROFILE ->
CONVERSATION OVERRIDE resolution, spec §20).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class ModelProfilePurpose(StrEnum):
    EXTRACTION = "extraction"
    # Phase 6: reserved for a future LLM-assisted document-drafting mode.
    # No code path calls an LLM for document composition today — see
    # ADR-0027 / app.documents.service's module docstring, which is a hard
    # constraint, not a Phase 6 change. A ProcessingProfileVersion may
    # reference a DOCUMENT_GENERATION ModelProfile purely as configuration
    # data; nothing in this phase ever reads it to make a provider call.
    DOCUMENT_GENERATION = "document_generation"


class ModelProfile(Base):
    """Spec §18. Phase 4 introduced this as a minimal foundation (single
    "extraction" purpose, admin-editable only via direct DB/seed script).
    Phase 6 makes it a real, admin-manageable, versioned entity: `PATCH
    /api/v1/model-profiles/{id}` (see app.profiles.router) updates the
    editable fields here AND snapshots the previous state into a new
    `ModelProfileVersion` row first — this table always holds "the current
    state", `model_profile_versions` holds "every state it was ever in and
    when", so a past `ProcessingRun.configuration_snapshot` referencing a
    `model_profile_id` remains explainable even after the profile is later
    edited."""

    __tablename__ = "model_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # "ollama" | "fake"
    model_identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Phase 6 additions (spec §18): whether/how the model should "think"
    # before answering (provider-specific hint, e.g. Ollama's `think`
    # option) and a free-form provider-specific configuration bag. Both
    # additive/nullable — an existing Phase 4 row defaults to NULL/None,
    # unchanged behavior.
    thinking_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ModelProfileVersion(Base):
    """Immutable snapshot of a `ModelProfile`'s editable fields at one point
    in time — written by `app.profiles.service.update_model_profile`
    BEFORE applying an edit, so it captures the state the profile was
    actually IN when whatever `ProcessingRun` referenced it ran. Never
    updated once written."""

    __tablename__ = "model_profile_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("model_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False)
    thinking_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessingProfile(Base):
    """Stable identity for one named preset (spec §19's "General",
    "Meeting", "Medical Consultation", "Psychotherapy", "Interview"
    examples). `is_system_default` marks the ONE profile the config
    hierarchy's SYSTEM DEFAULT layer resolves to when a conversation names
    no profile at all (see app.profiles.resolver) — exactly one should be
    true at a time, enforced by app.profiles.seed, not a DB constraint."""

    __tablename__ = "processing_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("processing_profile_versions.id", ondelete="SET NULL"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcessingProfileVersion(Base):
    """One immutable-once-published bundle of technical composition (spec
    §19): Speech + Diarization provider config, Extraction Model, (reserved)
    Document Model, Template + Template Version, Prompt + Prompt Version,
    Language, Retention Policy. Mirrors `app.templates.models.TemplateVersion`'s
    lifecycle exactly (DRAFT -> TEST -> PUBLISHED -> RETIRED, content frozen
    once published — see the `before_update` guard below)."""

    __tablename__ = "processing_profile_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    processing_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)

    # Speech/Diarization remain Settings-driven (see module docstring) —
    # stored here as a small, honestly-scoped config hint rather than a
    # real SpeechProfile/DiarizationProfile FK (that table is Phase 7).
    speech_provider_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    diarization_provider_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    extraction_model_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True
    )
    # Reserved (see ModelProfilePurpose.DOCUMENT_GENERATION docstring) —
    # never read by any runtime code path in this phase.
    document_model_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True
    )

    language: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    retention_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("retention_policies.id", ondelete="SET NULL"), nullable=True
    )

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


_PP_IMMUTABLE_FIELDS = (
    "speech_provider_config",
    "diarization_provider_config",
    "extraction_model_profile_id",
    "document_model_profile_id",
    "template_id",
    "template_version_id",
    "prompt_id",
    "prompt_version_id",
    "language",
    "retention_policy_id",
)


@event.listens_for(ProcessingProfileVersion, "before_update")
def _forbid_mutating_published_processing_profile_version(
    mapper: object, connection: object, target: ProcessingProfileVersion
) -> None:  # noqa: ARG001
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(target).attrs.status.history
    previous_status = history.deleted[0] if history.deleted else (
        history.unchanged[0] if history.unchanged else None
    )
    if previous_status in ("published", "retired"):
        attrs = sa_inspect(target).attrs
        if any(getattr(attrs, f).history.has_changes() for f in _PP_IMMUTABLE_FIELDS):
            raise RuntimeError(
                f"processing_profile_versions.id={target.id} is {previous_status!r} — its "
                "content can never be modified; create a new draft version instead"
            )
