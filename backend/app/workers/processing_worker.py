"""The Phase 3 worker process: dequeues a `ProcessingJob` id, executes the
corresponding pipeline stage (see app.processing.orchestrator), applies
the retry policy on failure, and chains the next stage on success. Never
runs inside an HTTP request — this is what `python -m
app.workers.runner` starts as its own process/container (see
deploy/docker-compose.yml's `worker-speech`/`worker-diarization`
services).

Concurrency: this loop processes exactly one job at a time per process
(safe default for GPU-heavy work — no risk of two jobs fighting over the
same VRAM). `Settings.worker_concurrency` documents the intended future
cap for a concurrent-execution implementation but is not yet read here —
scale out today via additional worker containers/replicas, not this
setting. See docs/admin/worker-configuration.md.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ai_providers import (
    get_diarization_provider,
    get_media_normalizer,
    get_speech_provider,
)
from app.core.storage import get_storage_provider
from app.media.normalizer import MediaNormalizer
from app.platform.config import get_settings
from app.platform.db.session import get_sessionmaker
from app.platform.valkey.backends import QueueBackend
from app.platform.valkey.valkey_backend import get_valkey_backend
from app.processing.models import JobType, ProcessingJob, ProcessingStatus
from app.processing.orchestrator import (
    execute_align,
    execute_diarize,
    execute_normalize,
    execute_transcribe,
    maybe_trigger_align,
    trigger_post_normalize,
)
from app.processing.outbox import relay_pending_outbox
from app.processing.retry import classify_exception
from app.processing.service import (
    complete_job,
    dequeue_next,
    fail_job,
    load_job,
    reclaim_stale_jobs,
    start_job,
)
from app.providers.diarization import DiarizationProvider
from app.providers.speech_to_text import SpeechToTextProvider
from app.providers.storage import StorageProvider

logger = logging.getLogger("vocadox.worker")

_STAGE_EXECUTORS = {
    JobType.NORMALIZE: "normalize",
    JobType.TRANSCRIBE: "transcribe",
    JobType.DIARIZE: "diarize",
    JobType.ALIGN: "align",
}


class ProcessingWorker:
    """All dependencies are injectable (defaulting to the real
    process-wide singletons) so tests can run the worker loop against an
    in-memory queue/DB/fake providers without any real Valkey/Postgres/GPU
    — see tests/processing/conftest.py's FakeQueueBackend."""

    def __init__(
        self,
        *,
        worker_id: str,
        job_types: list[JobType],
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        queue: QueueBackend | None = None,
        storage: StorageProvider | None = None,
        normalizer: MediaNormalizer | None = None,
        speech_provider: SpeechToTextProvider | None = None,
        diarization_provider: DiarizationProvider | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.job_types = job_types
        self._settings = get_settings()
        self._sessionmaker = sessionmaker or get_sessionmaker()
        self._queue = queue or get_valkey_backend()
        self._storage = storage or get_storage_provider()
        self._normalizer = normalizer or get_media_normalizer()
        self._speech_provider = speech_provider or get_speech_provider()
        self._diarization_provider = diarization_provider or get_diarization_provider()

    async def run_forever(self, *, max_iterations: int | None = None) -> None:
        """A transient infrastructure error (DB not migrated yet, a
        connection blip) here must never kill the whole worker process —
        found by real testing: a worker container started slightly before
        `alembic upgrade head` had run against a fresh database crashed
        outright on its first reclaim sweep, requiring a manual restart.
        Log and back off instead; the next iteration retries."""
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            try:
                await self._maintenance_sweep()
                job_id = await dequeue_next(self._queue, self.job_types, timeout_seconds=5)
            except Exception:  # noqa: BLE001 - infra hiccup, never crash the loop
                logger.exception("worker poll iteration failed; retrying")
                await asyncio.sleep(5)
                continue
            if job_id is None:
                continue
            await self._process_one(job_id)

    async def _maintenance_sweep(self) -> None:
        """Runs every loop iteration (bounded by the ~5s dequeue poll
        timeout below): reclaims stale-leased jobs, then relays any
        PENDING Transactional Outbox rows to Valkey (Phase 3.1 — see
        app.processing.outbox). Every worker process (both `worker-speech`
        and `worker-diarization`) runs this independently and
        redundantly — relay_pending_outbox is safe to call concurrently
        from multiple processes (see its docstring), so this is
        deliberately not centralized into a single relay process, which
        would just be a new single point of failure."""
        async with self._sessionmaker() as session:
            await reclaim_stale_jobs(session, self._queue)
            await session.commit()
        try:
            async with self._sessionmaker() as session:
                relayed = await relay_pending_outbox(session, self._queue)
                await session.commit()
                if relayed:
                    logger.info("outbox relay: published %d pending message(s)", relayed)
        except Exception:  # noqa: BLE001 - a relay hiccup (e.g. Valkey blip) must not
            # crash the worker loop or block reclaim/dequeue from continuing;
            # the un-committed transaction above already rolled any partially
            # claimed rows back to PENDING, so nothing is lost — just retried
            # next sweep (~5s later).
            logger.exception("outbox relay sweep failed; will retry next iteration")

    async def _process_one(self, job_id: uuid.UUID) -> None:
        async with self._sessionmaker() as session:
            job = await load_job(session, job_id)
            if job is None or job.status != ProcessingStatus.QUEUED.value:
                # Not necessarily a bug on its own (a job can legitimately
                # already be CANCELLED, or reclaimed by another worker) —
                # but also the observable symptom of a real dual-write
                # inconsistency found by fresh-install testing: if a
                # previous success-handler chain (e.g. NORMALIZE ->
                # trigger_post_normalize) pushed this job_id onto the
                # queue and then crashed *before* committing the row, the
                # DB row never exists (job is None) even though the Valkey
                # message did get sent. Logged rather than silently
                # discarded so an admin can tell "a queued message
                # referenced no job" apart from ordinary quiet operation —
                # see docs/operations/processing-troubleshooting.md.
                logger.warning(
                    "discarded a dequeued job_id with no matching QUEUED row",
                    extra={
                        "job_id": str(job_id),
                        "found": job is not None,
                        "status": job.status if job is not None else None,
                    },
                )
                return

            await start_job(
                session,
                job,
                worker_id=self.worker_id,
                lease_seconds=self._settings.job_lease_seconds,
            )
            await session.commit()

        async with self._sessionmaker() as session:
            job = await load_job(session, job_id)
            assert job is not None
            try:
                run_id = await self._dispatch(session, job)
                await complete_job(session, job, processing_run_id=run_id)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - classify and record, never crash the loop
                await session.rollback()
                async with self._sessionmaker() as fail_session:
                    job = await load_job(fail_session, job_id)
                    assert job is not None
                    failure_class = classify_exception(exc)
                    logger.warning(
                        "processing job failed",
                        extra={
                            "job_id": str(job.id),
                            "job_type": job.job_type,
                            "failure_class": failure_class.value,
                        },
                    )
                    retried = await fail_job(
                        fail_session,
                        job,
                        self._queue,
                        error_code=failure_class.value.upper(),
                        error_message_safe=f"{type(exc).__name__}: processing failed",
                        failure_class=failure_class,
                    )
                    from app.audit.service import record_event

                    await record_event(
                        fail_session,
                        event_type="processing.retried" if retried else "processing.failed",
                        event_metadata={
                            "job_id": str(job.id),
                            "job_type": job.job_type,
                            "failure_class": failure_class.value,
                        },
                    )
                    if not retried:
                        await self._mark_transcript_and_conversation_failed(fail_session, job)
                    await fail_session.commit()
                return

        try:
            async with self._sessionmaker() as session:
                job = await load_job(session, job_id)
                assert job is not None
                await self._on_success(session, job, run_id)
                await session.commit()
        except Exception:  # noqa: BLE001 - the job itself already succeeded and
            # committed above; a failure only in the *next*-stage chaining
            # (e.g. enqueueing TRANSCRIBE after NORMALIZE) must never crash
            # the worker process or be confused with the job's own failure.
            # Found by real testing: a mapper-configuration error triggered
            # here by a since-fixed startup bug took the whole worker down
            # even though the job it was chaining from had already
            # succeeded. The next reclaim/dequeue cycle continues normally;
            # the downstream stage simply won't have been enqueued yet,
            # which is surfaced to users as "stuck" processing rather than
            # a silent success — a real limitation, not swept under the rug.
            logger.exception(
                "post-success stage chaining failed",
                extra={"job_id": str(job_id)},
            )

    async def _dispatch(self, session: AsyncSession, job: ProcessingJob) -> uuid.UUID:
        job_type = JobType(job.job_type)
        if job_type == JobType.NORMALIZE:
            return await execute_normalize(session, self._storage, self._normalizer, job)
        if job_type == JobType.TRANSCRIBE:
            return await execute_transcribe(session, self._storage, self._speech_provider, job)
        if job_type == JobType.DIARIZE:
            return await execute_diarize(session, self._storage, self._diarization_provider, job)
        if job_type == JobType.ALIGN:
            return await execute_align(session, job)
        raise ValueError(f"unknown job_type: {job.job_type}")

    async def _on_success(
        self, session: AsyncSession, job: ProcessingJob, run_id: uuid.UUID
    ) -> None:
        job_type = JobType(job.job_type)
        if job_type == JobType.NORMALIZE:
            # run_id here is the NORMALIZATION ProcessingRun id; fetch its
            # output_media_id back out to chain TRANSCRIBE/DIARIZE.
            from app.processing.models import ProcessingRun

            run = await session.get(ProcessingRun, run_id)
            output_media_id = (
                (run.configuration_snapshot or {}).get("output_media_id") if run else None
            )
            if output_media_id:
                await trigger_post_normalize(
                    session, self._queue, job, normalized_media_id=uuid.UUID(output_media_id)
                )
        elif job_type in (JobType.TRANSCRIBE, JobType.DIARIZE):
            await maybe_trigger_align(session, self._queue, job)
        # ALIGN success needs no further chaining — it's the terminal stage.

    async def _mark_transcript_and_conversation_failed(
        self, session: AsyncSession, job: ProcessingJob
    ) -> None:
        from app.conversations.models import Conversation, ConversationStatus
        from app.conversations.state_machine import is_valid_transition
        from app.transcription.service import get_active_transcript, mark_transcript_failed

        transcript = await get_active_transcript(session, source_media_id=job.source_media_id)
        if transcript is not None:
            await mark_transcript_failed(
                session,
                transcript,
                error_code=job.error_code or "PROCESSING_FAILED",
                error_message_safe=job.error_message_safe or "processing failed",
            )
        conversation = await session.get(Conversation, job.conversation_id)
        if conversation is not None:
            current = ConversationStatus(conversation.status)
            if is_valid_transition(current, ConversationStatus.FAILED):
                conversation.status = ConversationStatus.FAILED.value
                await session.flush()


async def run_worker(
    *, worker_id: str, job_types: list[JobType], max_iterations: int | None = None
) -> None:
    worker = ProcessingWorker(worker_id=worker_id, job_types=job_types)
    await worker.run_forever(max_iterations=max_iterations)
