"""Template Engine domain (Phase 6, spec §42): `Template` is the stable
identity ("the General Conversation template"); `TemplateVersion` is one
immutable-once-published snapshot of its actual content (extraction
categories/fields + presentation rules) — mirrors
`app.documents.models.Document`/`DocumentRevision` exactly: a template is
never mutated in place once published, editing always creates a new DRAFT
version, and publishing never destroys the previous published version (it
is retired, not deleted, so every `ProcessingRun`/`DocumentRevision` that
recorded a `template_version_id` keeps a permanently resolvable, unchanged
reference for reproducibility).

`extraction_categories` is a JSON list of category definitions, each
either:
  - `{"key": ..., "builtin": true}` — reuses one of
    `app.intelligence.schemas.EXTRACTION_CATEGORIES` verbatim (its exact
    Pydantic schema class, unchanged) — this is how the "General
    Conversation" template stays byte-for-byte behaviorally identical to
    Phase 4/5's hardcoded categories (see app.templates.schema_builder).
  - `{"key": ..., "fact_type": ..., "item_field": ..., "instruction": ...,
    "fields": [{"name", "max_length", "description", "allow_not_mentioned"}]}`
    — a genuinely template-defined category, whose Pydantic schema is
    built dynamically at extraction time (app.templates.schema_builder) —
    this is how "Meeting" (and the Medical/Psychotherapy foundation-only
    templates) prove the Template Engine is real, not a renamed copy of
    General.

`presentation` is a JSON list of `{"category": ..., "title": ...}` in
render order — `app.documents.service.compose_document` reads this instead
of a hardcoded category->title mapping (see app.documents.service).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class VersionLifecycleStatus(StrEnum):
    """Shared lifecycle for every versioned Phase 6 entity (Template,
    Prompt, ProcessingProfile). Spec §43's prompt lifecycle
    (DRAFT -> TEST -> PUBLISHED -> RETIRED) generalizes cleanly to
    templates/processing profiles too, so one enum is reused rather than
    three near-identical ones."""

    DRAFT = "draft"
    TEST = "test"
    PUBLISHED = "published"
    RETIRED = "retired"


_ALLOWED_VERSION_TRANSITIONS: dict[VersionLifecycleStatus, set[VersionLifecycleStatus]] = {
    VersionLifecycleStatus.DRAFT: {VersionLifecycleStatus.TEST, VersionLifecycleStatus.PUBLISHED},
    VersionLifecycleStatus.TEST: {
        VersionLifecycleStatus.PUBLISHED,
        VersionLifecycleStatus.DRAFT,
    },
    VersionLifecycleStatus.PUBLISHED: {VersionLifecycleStatus.RETIRED},
    VersionLifecycleStatus.RETIRED: set(),
}


class InvalidVersionTransitionError(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition version from {current!r} to {target!r}")


def transition_version_status(
    current: VersionLifecycleStatus, target: VersionLifecycleStatus
) -> VersionLifecycleStatus:
    if current == target:
        return target
    if target not in _ALLOWED_VERSION_TRANSITIONS.get(current, set()):
        raise InvalidVersionTransitionError(current.value, target.value)
    return target


class ImmutablePublishedVersionError(RuntimeError):
    """A PUBLISHED or RETIRED version's content was about to be mutated.
    Once published, a version's `extraction_categories`/`presentation` (or
    the prompt-version equivalent content fields) must never change —
    editing always means creating a new DRAFT version. Enforced at the ORM
    level (see the `before_update` listeners below), not just by
    convention, matching `app.documents.models`'s
    `_forbid_mutating_approved_revision` precedent exactly."""


class Template(Base):
    """Stable identity for one template (e.g. "general", "meeting"). Never
    holds content itself — always delegate to the current published
    `TemplateVersion` (`current_published_version_id`)."""

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("template_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionLifecycleStatus.DRAFT.value, index=True
    )

    extraction_categories: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    presentation: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    review_rules: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(TemplateVersion, "before_update")
def _forbid_mutating_published_template_version(
    mapper: object, connection: object, target: TemplateVersion
) -> None:  # noqa: ARG001
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(target).attrs.status.history
    previous_status = history.deleted[0] if history.deleted else (
        history.unchanged[0] if history.unchanged else None
    )
    if previous_status in (
        VersionLifecycleStatus.PUBLISHED.value,
        VersionLifecycleStatus.RETIRED.value,
    ):
        content_history = sa_inspect(target).attrs
        content_changed = (
            content_history.extraction_categories.history.has_changes()
            or content_history.presentation.history.has_changes()
            or content_history.review_rules.history.has_changes()
        )
        if content_changed:
            raise ImmutablePublishedVersionError(
                f"template_versions.id={target.id} is {previous_status!r} — its content can "
                "never be modified; create a new draft version instead"
            )


class Prompt(Base):
    """Stable identity for one prompt (e.g. "extraction-general",
    "extraction-meeting") — spec §43."""

    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="extraction")
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PromptVersion(Base):
    """`system_prompt`/`category_instructions` mirror
    `app.intelligence.prompts.SYSTEM_PROMPT`/`_CATEGORY_INSTRUCTIONS`
    exactly in shape — the "general" prompt's published v1 content is
    those exact strings, so extraction behavior is unchanged unless an
    admin later publishes a new version (spec §43: DRAFT -> TEST ->
    PUBLISHED -> RETIRED, never overwrite a published prompt)."""

    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionLifecycleStatus.DRAFT.value, index=True
    )
    system_prompt: Mapped[str] = mapped_column(String(4096), nullable=False)
    category_instructions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(PromptVersion, "before_update")
def _forbid_mutating_published_prompt_version(
    mapper: object, connection: object, target: PromptVersion
) -> None:  # noqa: ARG001
    from sqlalchemy import inspect as sa_inspect

    history = sa_inspect(target).attrs.status.history
    previous_status = history.deleted[0] if history.deleted else (
        history.unchanged[0] if history.unchanged else None
    )
    if previous_status in (
        VersionLifecycleStatus.PUBLISHED.value,
        VersionLifecycleStatus.RETIRED.value,
    ):
        attrs = sa_inspect(target).attrs
        content_changed = (
            attrs.system_prompt.history.has_changes()
            or attrs.category_instructions.history.has_changes()
        )
        if content_changed:
            raise ImmutablePublishedVersionError(
                f"prompt_versions.id={target.id} is {previous_status!r} — its content can never "
                "be modified; create a new draft version instead"
            )
