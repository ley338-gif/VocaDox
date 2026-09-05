"""Admin-only Operations endpoints (Phase 11, roadmap §73): Worker/GPU/
Queue Metrics, Backup (create/list — restore is CLI-only, see
app.operations.backup_service), Retention Cleanup (run/list — dry-run by
default), Model Storage.

New RBAC permissions (spec: "restrict tightly, do not default-grant
broadly"): `operations:read` (metrics/model-storage/list views),
`backup:trigger` (create a backup), `retention-cleanup:trigger` (run
cleanup, dry-run or real), `retention-cleanup:read` (view past runs and
their item-level audit trail). None of these are granted to the "User"
or "Reviewer" roles — see app.identity.seed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.operations.backup_service import BackupError, create_backup
from app.operations.metrics_service import (
    gpu_metrics,
    model_storage_overview,
    queue_depth_by_job_type,
    queue_throughput_hourly,
    worker_throughput,
)
from app.operations.models import BackupRecord, RetentionCleanupItem, RetentionCleanupRun
from app.operations.retention_service import run_retention_cleanup
from app.operations.schemas import (
    BackupResponse,
    GpuMetrics,
    ModelStorageResponse,
    OperationsMetricsResponse,
    QueueDepthByType,
    QueueMetrics,
    QueueThroughputBucket,
    RetentionCleanupItemResponse,
    RetentionCleanupRunRequest,
    RetentionCleanupRunResponse,
    WorkerMetrics,
)
from app.platform.config import get_settings
from app.platform.db.session import get_session
from app.processing.queues import (
    DIARIZATION_WORKER_JOB_TYPES,
    EXTRACTION_WORKER_JOB_TYPES,
    SPEECH_WORKER_JOB_TYPES,
)
from app.providers.storage import StorageProvider

router = APIRouter(prefix="/admin/operations", tags=["operations"])

_require_operations_read = require_permission("operations:read")
_require_backup_trigger = require_permission("backup:trigger")
_require_retention_cleanup_trigger = require_permission("retention-cleanup:trigger")
_require_retention_cleanup_read = require_permission("retention-cleanup:read")

_WORKER_ROLES: list[tuple[str, list[str]]] = [
    ("worker-speech", [jt.value for jt in SPEECH_WORKER_JOB_TYPES]),
    ("worker-diarization", [jt.value for jt in DIARIZATION_WORKER_JOB_TYPES]),
    ("worker-extraction", [jt.value for jt in EXTRACTION_WORKER_JOB_TYPES]),
]


def _get_storage_provider() -> StorageProvider:
    # Local import to avoid a module-import-time cycle with app.core.storage
    # (mirrors app.administration.router's pattern of local imports for
    # cross-cutting helpers used in only one or two handlers).
    from app.core.storage import get_storage_provider

    return get_storage_provider()


# -- Metrics --------------------------------------------------------------


@router.get("/metrics", response_model=OperationsMetricsResponse)
async def operations_metrics_endpoint(
    _user: User = Depends(_require_operations_read),
    db: AsyncSession = Depends(get_session),
) -> OperationsMetricsResponse:
    from app.administration.service import worker_role_status

    workers = []
    for role, job_types in _WORKER_ROLES:
        base = await worker_role_status(db, role=role, job_types=job_types)
        throughput = await worker_throughput(db, job_types=job_types)
        workers.append(WorkerMetrics.model_validate({**base, **throughput}))

    queue = QueueMetrics(
        depth_by_job_type=[
            QueueDepthByType.model_validate(row) for row in await queue_depth_by_job_type(db)
        ],
        throughput_hourly=[
            QueueThroughputBucket.model_validate(row)
            for row in await queue_throughput_hourly(db)
        ],
    )
    return OperationsMetricsResponse(
        workers=workers, gpu=GpuMetrics.model_validate(gpu_metrics()), queue=queue
    )


# -- Model Storage ----------------------------------------------------------


@router.get("/model-storage", response_model=ModelStorageResponse)
async def model_storage_endpoint(
    _user: User = Depends(_require_operations_read),
) -> ModelStorageResponse:
    settings = get_settings()
    return ModelStorageResponse.model_validate(
        model_storage_overview(settings.model_volume_root)
    )


# -- Backup -----------------------------------------------------------------


@router.get("/backups", response_model=list[BackupResponse])
async def list_backups_endpoint(
    _user: User = Depends(_require_operations_read),
    db: AsyncSession = Depends(get_session),
) -> list[BackupResponse]:
    result = await db.execute(select(BackupRecord).order_by(BackupRecord.started_at.desc()))
    return [BackupResponse.model_validate(b) for b in result.scalars().all()]


@router.post("/backups", response_model=BackupResponse, status_code=status.HTTP_201_CREATED)
async def create_backup_endpoint(
    actor: User = Depends(_require_backup_trigger),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> BackupResponse:
    settings = get_settings()
    try:
        record = await create_backup(
            db,
            backup_root=settings.backup_root,
            database_url=settings.database_url,
            media_storage_root=settings.media_storage_root,
            pg_dump_path=settings.pg_dump_path,
            triggered_by_user_id=actor.id,
        )
    except BackupError as exc:
        await db.commit()  # persist the FAILED record even though the request itself errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"backup failed: {exc}"
        ) from exc
    await record_event(
        db,
        event_type="backup.created",
        user_id=actor.id,
        username=actor.username,
        event_metadata={
            "backup_id": str(record.id),
            "status": record.status,
            "database_dump_bytes": record.database_dump_bytes,
            "media_archive_bytes": record.media_archive_bytes,
        },
    )
    await db.commit()
    await db.refresh(record)
    return BackupResponse.model_validate(record)


# -- Retention Cleanup --------------------------------------------------------


@router.get("/retention-cleanup/runs", response_model=list[RetentionCleanupRunResponse])
async def list_retention_cleanup_runs_endpoint(
    _user: User = Depends(_require_retention_cleanup_read),
    db: AsyncSession = Depends(get_session),
) -> list[RetentionCleanupRunResponse]:
    result = await db.execute(
        select(RetentionCleanupRun).order_by(RetentionCleanupRun.started_at.desc())
    )
    return [RetentionCleanupRunResponse.model_validate(r) for r in result.scalars().all()]


@router.get(
    "/retention-cleanup/runs/{run_id}/items",
    response_model=list[RetentionCleanupItemResponse],
)
async def list_retention_cleanup_items_endpoint(
    run_id: uuid.UUID,
    _user: User = Depends(_require_retention_cleanup_read),
    db: AsyncSession = Depends(get_session),
) -> list[RetentionCleanupItemResponse]:
    run = await db.get(RetentionCleanupRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    result = await db.execute(
        select(RetentionCleanupItem)
        .where(RetentionCleanupItem.run_id == run_id)
        .order_by(RetentionCleanupItem.created_at)
    )
    return [RetentionCleanupItemResponse.model_validate(i) for i in result.scalars().all()]


@router.post(
    "/retention-cleanup/run",
    response_model=RetentionCleanupRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_retention_cleanup_endpoint(
    payload: RetentionCleanupRunRequest,
    actor: User = Depends(_require_retention_cleanup_trigger),
    db: AsyncSession = Depends(get_session),
    storage: StorageProvider = Depends(_get_storage_provider),
    _csrf: None = Depends(require_csrf),
) -> RetentionCleanupRunResponse:
    """`payload.dry_run` defaults to `true` (see RetentionCleanupRunRequest)
    — an admin must explicitly pass `dry_run: false` to perform real
    deletions. Every run, dry or real, is recorded and audited."""
    settings = get_settings()
    run = await run_retention_cleanup(
        db,
        storage,
        dry_run=payload.dry_run,
        triggered_by_user_id=actor.id,
        batch_size=settings.retention_cleanup_batch_size,
    )
    await record_event(
        db,
        event_type="retention_cleanup.run",
        user_id=actor.id,
        username=actor.username,
        event_metadata={
            "run_id": str(run.id),
            "dry_run": run.dry_run,
            "status": run.status,
            "conversations_evaluated": run.conversations_evaluated,
            "items_deleted": run.items_deleted,
            "bytes_freed": run.bytes_freed,
        },
    )
    if not run.dry_run and run.items_deleted:
        items_result = await db.execute(
            select(RetentionCleanupItem).where(RetentionCleanupItem.run_id == run.id)
        )
        for item in items_result.scalars().all():
            await record_event(
                db,
                event_type="retention_cleanup.item_deleted",
                user_id=actor.id,
                username=actor.username,
                event_metadata={
                    "run_id": str(run.id),
                    "conversation_id": str(item.conversation_id) if item.conversation_id else None,
                    "action": item.action,
                    "reason": item.reason,
                },
            )
    await db.commit()
    await db.refresh(run)
    return RetentionCleanupRunResponse.model_validate(run)
