"""Configuration Hierarchy (spec §20): `SYSTEM DEFAULT -> PROCESSING
PROFILE -> CONVERSATION OVERRIDE`. `resolve_effective_config` is the one
place any caller (extraction, composition, a future admin/debug view)
should go to answer "what configuration actually applies to this
conversation, and which layer decided each field" — never re-implement the
three-layer precedence inline elsewhere.

Layer precedence, per field, low to high:
  1. SYSTEM DEFAULT   — the one `ProcessingProfile` with `is_system_default`
     (seeded as "general" — see app.profiles.seed).
  2. PROCESSING PROFILE — `conversation.processing_profile_id`'s published
     version, if the conversation names one.
  3. CONVERSATION OVERRIDE — `conversation.config_overrides` JSON, keyed by
     the same field names as `EffectiveConfig`; any key present there wins
     over whatever the first two layers produced for that field alone
     (per-field override, not "replace the whole profile").

`EffectiveConfig.field_sources` records, per field, which of the three
layers actually set the value that won — the explainability spec §20
explicitly requires ("nachvollziehbar", not just "the override mechanically
applied").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.profiles.models import ProcessingProfile, ProcessingProfileVersion

ConfigSource = Literal["system_default", "processing_profile", "conversation_override"]

_FIELDS = (
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


class NoSystemDefaultProfileError(RuntimeError):
    """No `ProcessingProfile` is marked `is_system_default` — a seeding bug
    (app.profiles.seed always creates one), never a normal runtime state."""


@dataclass(frozen=True, slots=True)
class EffectiveConfig:
    processing_profile_id: uuid.UUID | None
    processing_profile_version_id: uuid.UUID | None
    speech_provider_config: dict[str, Any] | None
    diarization_provider_config: dict[str, Any] | None
    extraction_model_profile_id: uuid.UUID | None
    document_model_profile_id: uuid.UUID | None
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    prompt_id: uuid.UUID | None
    prompt_version_id: uuid.UUID | None
    language: str
    retention_policy_id: uuid.UUID | None
    field_sources: dict[str, ConfigSource] = field(default_factory=dict)

    def explain(self) -> list[dict[str, Any]]:
        """Human/admin-readable breakdown — one row per field, its winning
        value and which layer set it. Used by the effective-config debug
        endpoint (app.conversations.router)."""
        return [
            {"field": f, "value": _jsonable(getattr(self, f)), "source": self.field_sources.get(f)}
            for f in _FIELDS
        ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def _get_system_default_version(
    session: AsyncSession,
) -> tuple[ProcessingProfile, ProcessingProfileVersion]:
    result = await session.execute(
        select(ProcessingProfile).where(
            ProcessingProfile.is_system_default.is_(True), ProcessingProfile.enabled.is_(True)
        )
    )
    profile = result.scalars().first()
    if profile is None or profile.current_published_version_id is None:
        raise NoSystemDefaultProfileError(
            "no enabled system-default ProcessingProfile with a published version — "
            "run `python -m app.profiles.seed`"
        )
    version = await session.get(ProcessingProfileVersion, profile.current_published_version_id)
    if version is None:  # pragma: no cover - FK integrity guards this in practice
        raise NoSystemDefaultProfileError("system-default ProcessingProfile has no valid version")
    return profile, version


async def resolve_effective_config(
    session: AsyncSession, conversation: Conversation
) -> EffectiveConfig:
    """The full three-layer resolution for one conversation. Never raises
    for a conversation with no `processing_profile_id`/`config_overrides`
    set (both layers 2 and 3 are optional) — falls through cleanly to the
    system default, matching every pre-Phase-6 conversation's behavior."""
    default_profile, default_version = await _get_system_default_version(session)

    active_profile: ProcessingProfile = default_profile
    active_version: ProcessingProfileVersion = default_version
    sources: dict[str, ConfigSource] = dict.fromkeys(_FIELDS, "system_default")

    if conversation.processing_profile_id is not None:
        chosen_profile = await session.get(ProcessingProfile, conversation.processing_profile_id)
        if (
            chosen_profile is not None
            and chosen_profile.enabled
            and chosen_profile.current_published_version_id is not None
        ):
            chosen_version = await session.get(
                ProcessingProfileVersion, chosen_profile.current_published_version_id
            )
            if chosen_version is not None:
                active_profile = chosen_profile
                active_version = chosen_version
                sources = dict.fromkeys(_FIELDS, "processing_profile")

    values: dict[str, Any] = {f: getattr(active_version, f) for f in _FIELDS}

    overrides = conversation.config_overrides or {}
    for f in _FIELDS:
        if f in overrides and overrides[f] is not None:
            raw = overrides[f]
            if f.endswith("_id") and raw is not None and not isinstance(raw, uuid.UUID):
                raw = uuid.UUID(str(raw))
            values[f] = raw
            sources[f] = "conversation_override"

    return EffectiveConfig(
        processing_profile_id=active_profile.id,
        processing_profile_version_id=active_version.id,
        field_sources=sources,
        **values,
    )
