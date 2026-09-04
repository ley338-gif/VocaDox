"""Read-side accessor for the active ModelProfile — the only place worker
code should learn "which model to use" (spec: no hardcoded model
identifiers in worker code) — plus Phase 6's admin-facing CRUD/versioning
for ModelProfile and ProcessingProfile."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.identity.models import User
from app.profiles.models import (
    ModelProfile,
    ModelProfilePurpose,
    ModelProfileVersion,
    ProcessingProfile,
    ProcessingProfileVersion,
)

_MODEL_PROFILE_EDITABLE_FIELDS = (
    "name",
    "provider",
    "model_identifier",
    "context_length",
    "temperature",
    "max_tokens",
    "structured_output",
    "thinking_mode",
    "configuration",
    "enabled",
)


async def get_active_profile(
    session: AsyncSession, *, purpose: ModelProfilePurpose
) -> ModelProfile | None:
    result = await session.execute(
        select(ModelProfile)
        .where(ModelProfile.purpose == purpose.value, ModelProfile.enabled.is_(True))
        .order_by(ModelProfile.created_at.desc())
    )
    return result.scalars().first()


# -- ModelProfile CRUD/versioning (Phase 6) ----------------------------------


async def list_model_profiles(session: AsyncSession) -> list[ModelProfile]:
    result = await session.execute(select(ModelProfile).order_by(ModelProfile.created_at.asc()))
    return list(result.scalars().all())


async def create_model_profile(
    session: AsyncSession, *, created_by: User, **fields: Any
) -> ModelProfile:
    profile = ModelProfile(version="1", **fields)
    session.add(profile)
    await session.flush()
    session.add(
        ModelProfileVersion(
            model_profile_id=profile.id,
            version_number=1,
            created_by_user_id=created_by.id,
            **{f: getattr(profile, f) for f in _MODEL_PROFILE_EDITABLE_FIELDS},
        )
    )
    await session.flush()
    await record_event(
        session,
        event_type="model_profile.created",
        user_id=created_by.id,
        event_metadata={"model_profile_id": str(profile.id), "purpose": profile.purpose},
    )
    return profile


async def update_model_profile(
    session: AsyncSession, *, profile: ModelProfile, updated_by: User, **changes: Any
) -> ModelProfile:
    """Snapshots the CURRENT (pre-change) state into a new
    `ModelProfileVersion` FIRST, then applies `changes` — so
    `model_profile_versions` always has one row per distinct state the
    profile was ever actually in, including the very first (unversioned)
    Phase 4 seed state."""
    existing_versions = await session.execute(
        select(ModelProfileVersion.version_number)
        .where(ModelProfileVersion.model_profile_id == profile.id)
        .order_by(ModelProfileVersion.version_number.desc())
    )
    last_number = existing_versions.scalars().first() or 0

    for field_name, value in changes.items():
        if field_name in _MODEL_PROFILE_EDITABLE_FIELDS:
            setattr(profile, field_name, value)
    profile.version = str(last_number + 1)
    await session.flush()

    session.add(
        ModelProfileVersion(
            model_profile_id=profile.id,
            version_number=last_number + 1,
            created_by_user_id=updated_by.id,
            **{f: getattr(profile, f) for f in _MODEL_PROFILE_EDITABLE_FIELDS},
        )
    )
    await session.flush()
    await record_event(
        session,
        event_type="model_profile.updated",
        user_id=updated_by.id,
        event_metadata={"model_profile_id": str(profile.id), "fields": list(changes.keys())},
    )
    return profile


# -- ProcessingProfile CRUD/versioning (Phase 6, spec §19) -------------------


async def list_processing_profiles(session: AsyncSession) -> list[ProcessingProfile]:
    result = await session.execute(select(ProcessingProfile).order_by(ProcessingProfile.key.asc()))
    return list(result.scalars().all())


async def get_processing_profile_by_key(
    session: AsyncSession, key: str
) -> ProcessingProfile | None:
    result = await session.execute(select(ProcessingProfile).where(ProcessingProfile.key == key))
    return result.scalar_one_or_none()


async def list_processing_profile_versions(
    session: AsyncSession, processing_profile_id: uuid.UUID
) -> list[ProcessingProfileVersion]:
    result = await session.execute(
        select(ProcessingProfileVersion)
        .where(ProcessingProfileVersion.processing_profile_id == processing_profile_id)
        .order_by(ProcessingProfileVersion.version_number.asc())
    )
    return list(result.scalars().all())


async def create_processing_profile(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None,
    is_system_default: bool,
    created_by: User | None,
    **version_fields: Any,
) -> ProcessingProfile:
    profile = ProcessingProfile(
        key=key, name=name, description=description, is_system_default=is_system_default
    )
    session.add(profile)
    await session.flush()
    version = ProcessingProfileVersion(
        processing_profile_id=profile.id,
        version_number=1,
        status="draft",
        created_by_user_id=created_by.id if created_by else None,
        **version_fields,
    )
    session.add(version)
    await session.flush()
    return profile


async def create_draft_processing_profile_version(
    session: AsyncSession, *, profile: ProcessingProfile, created_by: User, **version_fields: Any
) -> ProcessingProfileVersion:
    existing = await list_processing_profile_versions(session, profile.id)
    next_number = (max((v.version_number for v in existing), default=0)) + 1
    version = ProcessingProfileVersion(
        processing_profile_id=profile.id,
        version_number=next_number,
        status="draft",
        created_by_user_id=created_by.id,
        **version_fields,
    )
    session.add(version)
    await session.flush()
    return version


async def publish_processing_profile_version(
    session: AsyncSession,
    *,
    profile: ProcessingProfile,
    version: ProcessingProfileVersion,
    published_by: User | None,
) -> ProcessingProfileVersion:
    from app.templates.models import VersionLifecycleStatus, transition_version_status

    version.status = transition_version_status(
        VersionLifecycleStatus(version.status), VersionLifecycleStatus.PUBLISHED
    ).value
    version.published_at = datetime.now(UTC)
    await session.flush()

    if profile.current_published_version_id is not None:
        previous = await session.get(
            ProcessingProfileVersion, profile.current_published_version_id
        )
        if previous is not None and previous.id != version.id:
            previous.status = VersionLifecycleStatus.RETIRED.value
            previous.retired_at = datetime.now(UTC)
            await session.flush()

    profile.current_published_version_id = version.id
    await session.flush()

    await record_event(
        session,
        event_type="processing_profile.published",
        user_id=published_by.id if published_by else None,
        event_metadata={
            "processing_profile_id": str(profile.id),
            "processing_profile_key": profile.key,
            "processing_profile_version_id": str(version.id),
            "version_number": version.version_number,
        },
    )
    return version
