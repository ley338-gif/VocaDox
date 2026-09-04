"""Admin-only provider status endpoints (spec: "Admin provider status
page" / "Provider health vs. platform readiness"). Deliberately separate
from `/health/ready` (app.platform.health) — an AI model not being
installed must never make the platform itself report unready; it's
surfaced here instead, admin-gated, with an honest "not installed" rather
than a fake "Healthy".

Phase 3 config is file/env-based only (Settings) — no provider
configuration UI exists yet (that's Phase 7); these endpoints are
read-only status, not configuration.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.administration.schemas import (
    AboutResponse,
    ComponentHealth,
    DashboardResponse,
    HardwareStatus,
    LLMProviderStatusResponse,
    ModelsOverviewResponse,
    ProcessingJobListResponse,
    ProcessingJobResponse,
    QueueCounts,
    RetentionPolicyCreateRequest,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
    StorageUsageResponse,
    WorkerRoleStatus,
    WorkersOverviewResponse,
)
from app.administration.service import (
    count_jobs,
    create_retention_policy,
    detect_cpu_count,
    detect_total_ram_mb,
    get_job,
    get_retention_policy,
    license_summary,
    list_jobs,
    list_retention_policies,
    queue_counts,
    resolve_repo_root,
    storage_usage,
    third_party_notices_excerpt,
    update_retention_policy,
    worker_role_status,
)
from app.core.ai_providers import get_diarization_provider, get_llm_provider, get_speech_provider
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.platform.config import get_settings
from app.platform.db.session import check_database_connectivity, get_session
from app.platform.valkey.valkey_backend import check_valkey_connectivity
from app.processing.models import JobType, ProcessingStatus
from app.processing.queues import (
    DIARIZATION_WORKER_JOB_TYPES,
    EXTRACTION_WORKER_JOB_TYPES,
    SPEECH_WORKER_JOB_TYPES,
)
from app.processing.service import retry_failed_job
from app.providers.device import detect_device_capabilities
from app.providers.diarization import DiarizationProvider
from app.providers.llm import LLMProvider
from app.providers.speech_to_text import SpeechToTextProvider

router = APIRouter(prefix="/admin/providers", tags=["administration"])
admin_router = APIRouter(prefix="/admin", tags=["administration"])

# Module-level singleton dependency (not called inline in a Depends()
# default, per the codebase's lint policy against B008).
_require_provider_read = require_permission("provider:read")
_require_system_admin = require_permission("system:admin")
_require_retention_read = require_permission("retention:read")
_require_retention_write = require_permission("retention:write")


class SpeechProviderStatusResponse(BaseModel):
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    device: str
    cuda_available: bool
    detail: str | None


class DiarizationProviderStatusResponse(BaseModel):
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    detail: str | None


@router.get("/speech", response_model=SpeechProviderStatusResponse)
async def speech_provider_status_endpoint(
    _user: User = Depends(_require_provider_read),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
) -> SpeechProviderStatusResponse:
    status_ = speech_provider.status()
    return SpeechProviderStatusResponse(
        provider=status_.provider,
        model=status_.model,
        model_revision=status_.model_revision,
        installed=status_.installed,
        device=status_.device,
        cuda_available=status_.cuda_available,
        detail=status_.detail,
    )


@router.get("/diarization", response_model=DiarizationProviderStatusResponse)
async def diarization_provider_status_endpoint(
    _user: User = Depends(_require_provider_read),
    diarization_provider: DiarizationProvider = Depends(get_diarization_provider),
) -> DiarizationProviderStatusResponse:
    status_ = diarization_provider.status()
    return DiarizationProviderStatusResponse(
        provider=status_.provider,
        model=status_.model,
        model_revision=status_.model_revision,
        installed=status_.installed,
        detail=status_.detail,
    )


@router.get("/llm", response_model=LLMProviderStatusResponse)
async def llm_provider_status_endpoint(
    _user: User = Depends(_require_provider_read),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> LLMProviderStatusResponse:
    status_ = llm_provider.status()
    return LLMProviderStatusResponse(
        provider=status_.provider,
        model=status_.model,
        model_revision=status_.model_revision,
        installed=status_.installed,
        device=status_.device,
        structured_output=status_.structured_output,
        detail=status_.detail,
    )


# -- Phase 7 Admin Portal ----------------------------------------------------


@admin_router.get("/models", response_model=ModelsOverviewResponse)
async def models_overview_endpoint(
    _user: User = Depends(_require_provider_read),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
    diarization_provider: DiarizationProvider = Depends(get_diarization_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ModelsOverviewResponse:
    """The Models/Speech/Diarization admin page's single data source —
    aggregates the three provider `.status()` calls Phase 3/4 already
    built. No model install/download logic here: that stays the Phase 3.1
    `model-manager` CLI's job (spec: "link to the existing model-manager
    CLI-based installation flow rather than reinventing model
    installation")."""
    speech = speech_provider.status()
    diarization = diarization_provider.status()
    llm = llm_provider.status()
    return ModelsOverviewResponse(
        speech={
            "provider": speech.provider,
            "model": speech.model,
            "model_revision": speech.model_revision,
            "installed": speech.installed,
            "device": speech.device,
            "cuda_available": speech.cuda_available,
            "detail": speech.detail,
        },
        diarization={
            "provider": diarization.provider,
            "model": diarization.model,
            "model_revision": diarization.model_revision,
            "installed": diarization.installed,
            "detail": diarization.detail,
        },
        llm=LLMProviderStatusResponse(
            provider=llm.provider,
            model=llm.model,
            model_revision=llm.model_revision,
            installed=llm.installed,
            device=llm.device,
            structured_output=llm.structured_output,
            detail=llm.detail,
        ),
    )


@admin_router.get("/dashboard", response_model=DashboardResponse)
async def dashboard_endpoint(
    _user: User = Depends(_require_system_admin),
    db: AsyncSession = Depends(get_session),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
    diarization_provider: DiarizationProvider = Depends(get_diarization_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> DashboardResponse:
    """Spec §49: real, live-checked component health (API/Postgres/Valkey/
    Speech/Diarization/LLM), real queue counts, a narrow hardware snapshot
    — and, per the hard privacy rule, NEVER any conversation/fact/
    transcript/document content. Every field below is a boolean/count/
    string label; nothing here reads conversation-scoped tables."""
    db_ok = await check_database_connectivity()
    valkey_ok = await check_valkey_connectivity()
    speech_status = speech_provider.status()
    diarization_status = diarization_provider.status()
    llm_status = llm_provider.status()

    components = [
        {"name": "api", "healthy": True, "detail": None},
        {"name": "postgresql", "healthy": db_ok, "detail": None if db_ok else "unreachable"},
        {"name": "valkey", "healthy": valkey_ok, "detail": None if valkey_ok else "unreachable"},
        {
            "name": "speech_provider",
            "healthy": speech_status.installed,
            "detail": speech_status.detail,
        },
        {
            "name": "diarization_provider",
            "healthy": diarization_status.installed,
            "detail": diarization_status.detail,
        },
        {"name": "llm_provider", "healthy": llm_status.installed, "detail": llm_status.detail},
    ]

    counts = await queue_counts(db)
    device_caps = detect_device_capabilities()

    return DashboardResponse(
        components=[ComponentHealth.model_validate(c) for c in components],
        queue=QueueCounts(**counts),
        hardware=HardwareStatus(
            cpu_count=detect_cpu_count(),
            total_ram_mb=detect_total_ram_mb(),
            cuda_available=device_caps.cuda_available,
            gpu_device_name=device_caps.device_name,
            total_vram_mb=device_caps.total_vram_mb,
            free_vram_mb=device_caps.free_vram_mb,
        ),
        application_version=_application_version(),
    )


def _application_version() -> str:
    from app.platform.version import APPLICATION_VERSION

    return APPLICATION_VERSION


# -- Jobs ---------------------------------------------------------------


@admin_router.get("/jobs", response_model=ProcessingJobListResponse)
async def list_jobs_endpoint(
    _user: User = Depends(_require_system_admin),
    db: AsyncSession = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status"),
    job_type_filter: str | None = Query(default=None, alias="job_type"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ProcessingJobListResponse:
    if status_filter is not None and status_filter not in {s.value for s in ProcessingStatus}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid status")
    if job_type_filter is not None and job_type_filter not in {j.value for j in JobType}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid job_type")
    jobs = await list_jobs(
        db, status_filter=status_filter, job_type_filter=job_type_filter, limit=limit, offset=offset
    )
    total = await count_jobs(db, status_filter=status_filter, job_type_filter=job_type_filter)
    return ProcessingJobListResponse(
        items=[ProcessingJobResponse.model_validate(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post("/jobs/{job_id}/retry", response_model=ProcessingJobResponse)
async def retry_job_endpoint(
    job_id: uuid.UUID,
    actor: User = Depends(_require_system_admin),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ProcessingJobResponse:
    """Admin-initiated retry of a terminally FAILED job (see
    app.processing.service.retry_failed_job — reuses the exact same
    outbox-relay dispatch mechanism the automatic retry path uses, never a
    parallel enqueue mechanism)."""
    from app.audit.service import record_event
    from app.core.ai_providers import get_queue_backend

    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    retried = await retry_failed_job(db, get_queue_backend(), job)
    if not retried:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="only a FAILED job can be retried"
        )
    await record_event(
        db,
        event_type="processing_job.retried",
        user_id=actor.id,
        username=actor.username,
        event_metadata={"job_id": str(job.id), "job_type": job.job_type},
    )
    await db.commit()
    await db.refresh(job)
    return ProcessingJobResponse.model_validate(job)


# -- Workers --------------------------------------------------------------

_WORKER_ROLES: list[tuple[str, list[str]]] = [
    ("worker-speech", [jt.value for jt in SPEECH_WORKER_JOB_TYPES]),
    ("worker-diarization", [jt.value for jt in DIARIZATION_WORKER_JOB_TYPES]),
    ("worker-extraction", [jt.value for jt in EXTRACTION_WORKER_JOB_TYPES]),
]


@admin_router.get("/workers", response_model=WorkersOverviewResponse)
async def workers_overview_endpoint(
    _user: User = Depends(_require_system_admin),
    db: AsyncSession = Depends(get_session),
) -> WorkersOverviewResponse:
    """Derived from `ProcessingJob` rows already written by Phase 3's
    worker processes — no new worker-registry table (spec: "avoid
    building a hardware inventory platform")."""
    workers = [
        WorkerRoleStatus.model_validate(
            await worker_role_status(db, role=role, job_types=job_types)
        )
        for role, job_types in _WORKER_ROLES
    ]
    return WorkersOverviewResponse(workers=workers)


# -- Storage --------------------------------------------------------------


@admin_router.get("/storage", response_model=StorageUsageResponse)
async def storage_usage_endpoint(
    _user: User = Depends(_require_system_admin),
) -> StorageUsageResponse:
    settings = get_settings()
    usage = storage_usage(
        media_storage_root=settings.media_storage_root,
        model_volume_root=settings.model_volume_root,
    )
    return StorageUsageResponse.model_validate(usage)


# -- Retention Policies -----------------------------------------------------


@admin_router.get("/retention-policies", response_model=list[RetentionPolicyResponse])
async def list_retention_policies_endpoint(
    _user: User = Depends(_require_retention_read),
    db: AsyncSession = Depends(get_session),
) -> list[RetentionPolicyResponse]:
    return [RetentionPolicyResponse.model_validate(p) for p in await list_retention_policies(db)]


@admin_router.post(
    "/retention-policies",
    response_model=RetentionPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_retention_policy_endpoint(
    payload: RetentionPolicyCreateRequest,
    _user: User = Depends(_require_retention_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> RetentionPolicyResponse:
    policy = await create_retention_policy(db, **payload.model_dump())
    await db.commit()
    await db.refresh(policy)
    return RetentionPolicyResponse.model_validate(policy)


@admin_router.patch("/retention-policies/{policy_id}", response_model=RetentionPolicyResponse)
async def update_retention_policy_endpoint(
    policy_id: uuid.UUID,
    payload: RetentionPolicyUpdateRequest,
    _user: User = Depends(_require_retention_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> RetentionPolicyResponse:
    policy = await get_retention_policy(db, policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="retention policy not found"
        )
    changes = payload.model_dump(exclude_unset=True)
    policy = await update_retention_policy(db, policy, _fields_set=set(changes.keys()), **changes)
    await db.commit()
    await db.refresh(policy)
    return RetentionPolicyResponse.model_validate(policy)


# -- About & Licenses --------------------------------------------------------


@admin_router.get("/about", response_model=AboutResponse)
async def about_endpoint(
    _user: User = Depends(_require_system_admin),
) -> AboutResponse:
    repo_root = resolve_repo_root()
    return AboutResponse(
        application_version=_application_version(),
        license_summary=license_summary(repo_root / "compliance"),
        third_party_notices_excerpt=third_party_notices_excerpt(repo_root),
    )
