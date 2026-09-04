"""REST endpoints for the Model Profile / Processing Profile admin surface
(spec §18/§19). Global (platform-wide), not organization-scoped. Gated by
`model-profile:read`/`model-profile:write` and
`processing-profile:read`/`processing-profile:write` — never open to every
user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.platform.db.session import get_session
from app.profiles.api_schemas import (
    ModelProfileCreateRequest,
    ModelProfileResponse,
    ModelProfileUpdateRequest,
    ModelProfileVersionResponse,
    ProcessingProfileCreateRequest,
    ProcessingProfileResponse,
    ProcessingProfileVersionCreateRequest,
    ProcessingProfileVersionResponse,
)
from app.profiles.models import (
    ModelProfile,
    ModelProfileVersion,
    ProcessingProfile,
    ProcessingProfileVersion,
)
from app.profiles.service import (
    create_draft_processing_profile_version,
    create_model_profile,
    create_processing_profile,
    get_processing_profile_by_key,
    list_model_profiles,
    list_processing_profile_versions,
    list_processing_profiles,
    publish_processing_profile_version,
    update_model_profile,
)
from app.templates.models import InvalidVersionTransitionError

router = APIRouter(prefix="/model-profiles", tags=["profiles"])
processing_router = APIRouter(prefix="/processing-profiles", tags=["profiles"])

_require_model_profile_read = require_permission("model-profile:read")
_require_model_profile_write = require_permission("model-profile:write")
_require_processing_profile_read = require_permission("processing-profile:read")
_require_processing_profile_write = require_permission("processing-profile:write")


@router.get("", response_model=list[ModelProfileResponse])
async def list_model_profiles_endpoint(
    _user: User = Depends(_require_model_profile_read),
    db: AsyncSession = Depends(get_session),
) -> list[ModelProfileResponse]:
    return [ModelProfileResponse.model_validate(p) for p in await list_model_profiles(db)]


@router.post("", response_model=ModelProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_model_profile_endpoint(
    payload: ModelProfileCreateRequest,
    user: User = Depends(_require_model_profile_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ModelProfileResponse:
    profile = await create_model_profile(db, created_by=user, **payload.model_dump())
    await db.commit()
    await db.refresh(profile)
    return ModelProfileResponse.model_validate(profile)


async def _get_model_profile_or_404(db: AsyncSession, model_profile_id: uuid.UUID) -> ModelProfile:
    profile = await db.get(ModelProfile, model_profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model profile not found")
    return profile


@router.get("/{model_profile_id}", response_model=ModelProfileResponse)
async def get_model_profile_endpoint(
    model_profile_id: uuid.UUID,
    _user: User = Depends(_require_model_profile_read),
    db: AsyncSession = Depends(get_session),
) -> ModelProfileResponse:
    return ModelProfileResponse.model_validate(
        await _get_model_profile_or_404(db, model_profile_id)
    )


@router.patch("/{model_profile_id}", response_model=ModelProfileResponse)
async def update_model_profile_endpoint(
    model_profile_id: uuid.UUID,
    payload: ModelProfileUpdateRequest,
    user: User = Depends(_require_model_profile_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ModelProfileResponse:
    """Snapshots the pre-change state into a new `ModelProfileVersion`
    before applying the edit — see app.profiles.service.update_model_profile."""
    profile = await _get_model_profile_or_404(db, model_profile_id)
    changes = payload.model_dump(exclude_unset=True)
    profile = await update_model_profile(db, profile=profile, updated_by=user, **changes)
    await db.commit()
    await db.refresh(profile)
    return ModelProfileResponse.model_validate(profile)


@router.get("/{model_profile_id}/versions", response_model=list[ModelProfileVersionResponse])
async def list_model_profile_versions_endpoint(
    model_profile_id: uuid.UUID,
    _user: User = Depends(_require_model_profile_read),
    db: AsyncSession = Depends(get_session),
) -> list[ModelProfileVersionResponse]:
    from sqlalchemy import select

    await _get_model_profile_or_404(db, model_profile_id)
    result = await db.execute(
        select(ModelProfileVersion)
        .where(ModelProfileVersion.model_profile_id == model_profile_id)
        .order_by(ModelProfileVersion.version_number.asc())
    )
    return [ModelProfileVersionResponse.model_validate(v) for v in result.scalars().all()]


# -- Processing Profiles ------------------------------------------------


@processing_router.get("", response_model=list[ProcessingProfileResponse])
async def list_processing_profiles_endpoint(
    _user: User = Depends(_require_processing_profile_read),
    db: AsyncSession = Depends(get_session),
) -> list[ProcessingProfileResponse]:
    """The friendly, end-user-facing list (spec §19: "User sieht
    verständliche Namen") — used to populate the profile picker when
    starting a conversation. Deliberately readable with the same
    `processing-profile:read` permission granted to the standard "User"
    role, not admin-only (only WRITE is admin-gated)."""
    return [
        ProcessingProfileResponse.model_validate(p) for p in await list_processing_profiles(db)
    ]


async def _get_processing_profile_or_404(
    db: AsyncSession, processing_profile_id: uuid.UUID
) -> ProcessingProfile:
    profile = await db.get(ProcessingProfile, processing_profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="processing profile not found"
        )
    return profile


@processing_router.post(
    "", response_model=ProcessingProfileResponse, status_code=status.HTTP_201_CREATED
)
async def create_processing_profile_endpoint(
    payload: ProcessingProfileCreateRequest,
    user: User = Depends(_require_processing_profile_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ProcessingProfileResponse:
    if await get_processing_profile_by_key(db, payload.key) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"processing profile key {payload.key!r} exists",
        )
    fields = payload.model_dump(exclude={"key", "name", "description", "is_system_default"})
    profile = await create_processing_profile(
        db,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        is_system_default=payload.is_system_default,
        created_by=user,
        **fields,
    )
    await db.commit()
    await db.refresh(profile)
    return ProcessingProfileResponse.model_validate(profile)


@processing_router.get("/{processing_profile_id}", response_model=ProcessingProfileResponse)
async def get_processing_profile_endpoint(
    processing_profile_id: uuid.UUID,
    _user: User = Depends(_require_processing_profile_read),
    db: AsyncSession = Depends(get_session),
) -> ProcessingProfileResponse:
    return ProcessingProfileResponse.model_validate(
        await _get_processing_profile_or_404(db, processing_profile_id)
    )


@processing_router.get(
    "/{processing_profile_id}/versions", response_model=list[ProcessingProfileVersionResponse]
)
async def list_processing_profile_versions_endpoint(
    processing_profile_id: uuid.UUID,
    _user: User = Depends(_require_processing_profile_read),
    db: AsyncSession = Depends(get_session),
) -> list[ProcessingProfileVersionResponse]:
    await _get_processing_profile_or_404(db, processing_profile_id)
    return [
        ProcessingProfileVersionResponse.model_validate(v)
        for v in await list_processing_profile_versions(db, processing_profile_id)
    ]


@processing_router.post(
    "/{processing_profile_id}/versions",
    response_model=ProcessingProfileVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_processing_profile_version_endpoint(
    processing_profile_id: uuid.UUID,
    payload: ProcessingProfileVersionCreateRequest,
    user: User = Depends(_require_processing_profile_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ProcessingProfileVersionResponse:
    profile = await _get_processing_profile_or_404(db, processing_profile_id)
    version = await create_draft_processing_profile_version(
        db, profile=profile, created_by=user, **payload.model_dump()
    )
    await db.commit()
    await db.refresh(version)
    return ProcessingProfileVersionResponse.model_validate(version)


@processing_router.post(
    "/{processing_profile_id}/versions/{version_id}/publish",
    response_model=ProcessingProfileVersionResponse,
)
async def publish_processing_profile_version_endpoint(
    processing_profile_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(_require_processing_profile_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ProcessingProfileVersionResponse:
    profile = await _get_processing_profile_or_404(db, processing_profile_id)
    version = await db.get(ProcessingProfileVersion, version_id)
    if version is None or version.processing_profile_id != processing_profile_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="processing profile version not found"
        )
    try:
        published = await publish_processing_profile_version(
            db, profile=profile, version=version, published_by=user
        )
    except InvalidVersionTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(published)
    return ProcessingProfileVersionResponse.model_validate(published)
