"""ProcessingJob orchestration: creation, idempotency, queue dispatch,
lease/heartbeat-based worker-crash recovery, and retry application.

Domain code depends only on `QueueBackend` (never Valkey directly — see
app.platform.valkey). All DB writes here are `flush()`, not `commit()` —
callers commit (matching the rest of the codebase's transaction pattern,
e.g. app.media.service).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.valkey.backends import QueueBackend
from app.processing.models import FailureClass, JobType, ProcessingJob, ProcessingStatus
from app.processing.queues import queue_name_for
from app.processing.retry import is_retryable


async def get_active_job(
    session: AsyncSession, *, source_media_id: uuid.UUID, job_type: JobType
) -> ProcessingJob | None:
    """The one non-terminal (QUEUED/RUNNING) job of this type for this
    source, if any — used for idempotency: repeated POST /process must not
    create unlimited duplicate active jobs (spec, "Job idempotency")."""
    result = await session.execute(
        select(ProcessingJob).where(
            ProcessingJob.source_media_id == source_media_id,
            ProcessingJob.job_type == job_type.value,
            ProcessingJob.status.in_([ProcessingStatus.QUEUED.value, ProcessingStatus.RUNNING.value]),
        )
    )
    return result.scalars().first()


async def count_active_jobs_for_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(ProcessingJob).where(
            ProcessingJob.conversation_id == conversation_id,
            ProcessingJob.status.in_([ProcessingStatus.QUEUED.value, ProcessingStatus.RUNNING.value]),
        )
    )
    return len(result.scalars().all())


async def create_and_enqueue_job(
    session: AsyncSession,
    queue: QueueBackend,
    *,
    conversation_id: uuid.UUID,
    source_media_id: uuid.UUID,
    job_type: JobType,
    created_by_user_id: uuid.UUID | None,
    job_metadata: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> ProcessingJob:
    job = ProcessingJob(
        conversation_id=conversation_id,
        source_media_id=source_media_id,
        job_type=job_type.value,
        status=ProcessingStatus.QUEUED.value,
        attempt=0,
        max_attempts=max_attempts,
        job_metadata=job_metadata,
        created_by_user_id=created_by_user_id,
    )
    session.add(job)
    await session.flush()
    await queue.enqueue(queue_name_for(job_type), str(job.id))
    return job


async def get_or_create_job(
    session: AsyncSession,
    queue: QueueBackend,
    *,
    conversation_id: uuid.UUID,
    source_media_id: uuid.UUID,
    job_type: JobType,
    created_by_user_id: uuid.UUID | None,
    job_metadata: dict[str, Any] | None = None,
) -> ProcessingJob:
    """Idempotent: reuses an existing active job of this type/source
    instead of creating a duplicate."""
    existing = await get_active_job(session, source_media_id=source_media_id, job_type=job_type)
    if existing is not None:
        return existing
    return await create_and_enqueue_job(
        session,
        queue,
        conversation_id=conversation_id,
        source_media_id=source_media_id,
        job_type=job_type,
        created_by_user_id=created_by_user_id,
        job_metadata=job_metadata,
    )


async def dequeue_next(
    queue: QueueBackend, job_types: list[JobType], *, timeout_seconds: int = 5
) -> uuid.UUID | None:
    """Poll each of `job_types`' queues briefly in turn. Simple, not
    perfectly fair under heavy load across >1 queue, but adequate for the
    small worker counts this phase targets (spec: "don't overengineer")."""
    per_queue_timeout = max(1, timeout_seconds // max(1, len(job_types)))
    for job_type in job_types:
        payload = await queue.dequeue(queue_name_for(job_type), timeout_seconds=per_queue_timeout)
        if payload:
            try:
                return uuid.UUID(payload)
            except ValueError:
                continue
    return None


async def load_job(session: AsyncSession, job_id: uuid.UUID) -> ProcessingJob | None:
    return await session.get(ProcessingJob, job_id)


async def start_job(
    session: AsyncSession, job: ProcessingJob, *, worker_id: str, lease_seconds: int
) -> None:
    job.status = ProcessingStatus.RUNNING.value
    job.attempt += 1
    job.started_at = datetime.now(UTC)
    job.worker_id = worker_id
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    job.progress = 0
    await session.flush()


async def heartbeat_job(session: AsyncSession, job: ProcessingJob, *, lease_seconds: int) -> None:
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    await session.flush()


async def update_progress(session: AsyncSession, job: ProcessingJob, *, progress: int) -> None:
    job.progress = max(0, min(100, progress))
    await session.flush()


async def complete_job(
    session: AsyncSession, job: ProcessingJob, *, processing_run_id: uuid.UUID | None = None
) -> None:
    job.status = ProcessingStatus.SUCCEEDED.value
    job.progress = 100
    job.completed_at = datetime.now(UTC)
    job.processing_run_id = processing_run_id
    job.lease_expires_at = None
    await session.flush()


async def fail_job(
    session: AsyncSession,
    job: ProcessingJob,
    queue: QueueBackend,
    *,
    error_code: str,
    error_message_safe: str,
    failure_class: FailureClass,
) -> bool:
    """Apply the retry policy: retry (requeue, return True) or terminally
    fail (return False)."""
    job.error_code = error_code
    job.error_message_safe = error_message_safe
    job.failure_class = failure_class.value
    job.lease_expires_at = None

    if is_retryable(failure_class) and job.attempt < job.max_attempts:
        job.status = ProcessingStatus.QUEUED.value
        job.started_at = None
        job.worker_id = None
        await session.flush()
        await queue.enqueue(queue_name_for(JobType(job.job_type)), str(job.id))
        return True

    job.status = ProcessingStatus.FAILED.value
    job.completed_at = datetime.now(UTC)
    await session.flush()
    return False


async def cancel_queued_job(session: AsyncSession, job: ProcessingJob) -> bool:
    """Only QUEUED jobs can be cancelled cleanly (spec: "QUEUED-job
    cancellation should be straightforward, running-GPU-process
    cancellation may be harder — don't claim cancellation capability you
    haven't implemented"). A RUNNING job is left alone; callers get False
    and must not claim it was cancelled."""
    if job.status != ProcessingStatus.QUEUED.value:
        return False
    job.status = ProcessingStatus.CANCELLED.value
    job.completed_at = datetime.now(UTC)
    await session.flush()
    return True


async def reclaim_stale_jobs(
    session: AsyncSession, queue: QueueBackend, *, now: datetime | None = None
) -> list[ProcessingJob]:
    """Worker-crash recovery: a RUNNING job whose lease has expired (the
    worker that held it stopped heartbeating — crashed, killed, network
    partition) is requeued rather than left stuck RUNNING forever."""
    now = now or datetime.now(UTC)
    result = await session.execute(
        select(ProcessingJob).where(
            ProcessingJob.status == ProcessingStatus.RUNNING.value,
            ProcessingJob.lease_expires_at.is_not(None),
            ProcessingJob.lease_expires_at < now,
        )
    )
    stale = list(result.scalars().all())
    for job in stale:
        job.error_code = "WORKER_LEASE_EXPIRED"
        job.error_message_safe = "worker did not renew its lease in time (likely crashed)"
        job.failure_class = FailureClass.TRANSIENT.value
        job.lease_expires_at = None
        if job.attempt < job.max_attempts:
            job.status = ProcessingStatus.QUEUED.value
            job.started_at = None
            job.worker_id = None
            await queue.enqueue(queue_name_for(JobType(job.job_type)), str(job.id))
        else:
            job.status = ProcessingStatus.FAILED.value
            job.completed_at = now
    if stale:
        await session.flush()
    return stale


def serialize_job_metadata(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True)
