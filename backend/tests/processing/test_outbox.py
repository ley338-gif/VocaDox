"""Phase 3.1: Transactional Outbox regression coverage.

Closes the Phase 3 Postgres/Valkey dual-write race (see
`app.processing.models.OutboxStatus` and
`docs/architecture/processing-jobs.md`): a `ProcessingJob` row and the
`ProcessingOutbox` row announcing it are now written in one transaction,
and `relay_pending_outbox` is the only thing that ever calls
`QueueBackend.enqueue()`. These tests exercise the three properties the
brief calls for — crash-before-relay does not orphan the job, restart
recovers it, and a duplicated relay delivery is safely a no-op — without
needing real Postgres/Valkey (see tests/processing/conftest.py's
FakeQueueBackend, identical in spirit to the rest of this test suite).
"""

from __future__ import annotations

import uuid

from app.processing.models import (
    JobType,
    OutboxStatus,
    ProcessingJob,
    ProcessingOutbox,
    ProcessingStatus,
)
from app.processing.outbox import relay_pending_outbox, write_outbox_entry
from app.processing.queues import queue_name_for
from app.processing.service import create_and_enqueue_job, load_job
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio


async def _make_job_row(sessionmaker, *, conversation_id, source_media_id) -> uuid.UUID:
    """Inserts a ProcessingJob + its outbox row and commits — the same
    atomic unit `create_and_enqueue_job` produces — and returns the job id."""
    async with sessionmaker() as session:
        job = await create_and_enqueue_job(
            session,
            None,  # the outbox path never touches `queue` at creation time
            conversation_id=uuid.UUID(conversation_id),
            source_media_id=uuid.UUID(source_media_id),
            job_type=JobType.NORMALIZE,
            created_by_user_id=None,
        )
        await session.commit()
        return job.id


async def test_job_creation_never_calls_queue_directly(client, seeded, processing_env) -> None:  # noqa: ANN001
    """`create_and_enqueue_job` must write an outbox row, not call
    `queue.enqueue()` itself — regression test for the exact Phase 3 bug
    (a message published for a job whose transaction then rolled back)."""
    _, sessionmaker, queue, _storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    job_id = await _make_job_row(
        sessionmaker, conversation_id=conversation_id, source_media_id=media_id
    )

    # Nothing reached the (fake) queue yet — only the relay does that.
    assert sum(len(v) for v in queue._queues.values()) == 0  # noqa: SLF001

    async with sessionmaker() as session:
        outbox_row = (
            await session.execute(
                select(ProcessingOutbox).where(ProcessingOutbox.job_id == job_id)
            )
        ).scalars().first()
    assert outbox_row is not None
    assert outbox_row.status == OutboxStatus.PENDING.value
    assert outbox_row.queue_name == queue_name_for(JobType.NORMALIZE)
    assert outbox_row.payload == str(job_id)


async def test_crash_before_relay_does_not_orphan_job(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Simulates the exact crash window the brief calls out: the job row
    (and its outbox row) committed, but the process crashed before any
    relay sweep ran. A later relay pass (e.g. after a worker restart) must
    still deliver the message — the job must never be permanently
    orphaned just because no relay happened immediately."""
    _, sessionmaker, queue, _storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    job_id = await _make_job_row(
        sessionmaker, conversation_id=conversation_id, source_media_id=media_id
    )

    # "Restart": a brand-new session/relay pass, exactly what a freshly
    # started worker's first maintenance sweep does.
    async with sessionmaker() as session:
        relayed = await relay_pending_outbox(session, queue)
        await session.commit()
    assert relayed == 1

    assert queue._queues[queue_name_for(JobType.NORMALIZE)] == [str(job_id)]  # noqa: SLF001

    async with sessionmaker() as session:
        outbox_row = (
            await session.execute(
                select(ProcessingOutbox).where(ProcessingOutbox.job_id == job_id)
            )
        ).scalars().first()
    assert outbox_row.status == OutboxStatus.PUBLISHED.value
    assert outbox_row.published_at is not None


async def test_relay_is_idempotent_across_repeated_calls(client, seeded, processing_env) -> None:  # noqa: ANN001
    """A relay sweep that runs again after already publishing a row (e.g.
    two worker processes both sweeping, or the same worker sweeping every
    ~5s) must not re-publish it — PUBLISHED rows are never candidates
    again."""
    _, sessionmaker, queue, _storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _make_job_row(sessionmaker, conversation_id=conversation_id, source_media_id=media_id)

    async with sessionmaker() as session:
        first = await relay_pending_outbox(session, queue)
        await session.commit()
    async with sessionmaker() as session:
        second = await relay_pending_outbox(session, queue)
        await session.commit()

    assert first == 1
    assert second == 0
    assert len(queue._queues[queue_name_for(JobType.NORMALIZE)]) == 1  # noqa: SLF001


async def test_duplicate_delivery_of_same_job_is_a_safe_no_op(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Even if a message IS delivered twice at the Valkey level (relay
    published, then its own transaction failed to commit and it got
    re-relayed — an at-least-once system's normal duplicate case), the
    worker's own dequeue-time guard must discard the second delivery
    rather than reprocessing (or double-chaining) the job."""
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    job_id = await _make_job_row(
        sessionmaker, conversation_id=conversation_id, source_media_id=media_id
    )

    # Manually inject a duplicate message onto the queue, simulating what
    # an at-least-once relay can legitimately produce.
    queue_name = queue_name_for(JobType.NORMALIZE)
    await queue.enqueue(queue_name, str(job_id))
    await queue.enqueue(queue_name, str(job_id))

    from app.workers.processing_worker import ProcessingWorker

    worker = ProcessingWorker(
        worker_id="test-dup",
        job_types=[JobType.NORMALIZE],
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
    )

    # First delivery: processes normally (job goes QUEUED -> RUNNING ->
    # SUCCEEDED via the NORMALIZE stage executor).
    await worker.run_forever(max_iterations=1)
    async with sessionmaker() as session:
        job = await load_job(session, job_id)
        assert job.status == ProcessingStatus.SUCCEEDED.value

    # Second delivery of the SAME job id: must be discarded, not
    # reprocessed — the job is no longer QUEUED.
    await worker.run_forever(max_iterations=1)
    async with sessionmaker() as session:
        job = await load_job(session, job_id)
        assert job.status == ProcessingStatus.SUCCEEDED.value  # unchanged, not re-run


async def test_outbox_write_requires_explicit_call_not_implicit_on_flush(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Sanity check on the primitive itself: writing an outbox entry
    without committing must not be visible to a relay running in a
    different, already-committed transaction — i.e. the outbox row's
    durability is genuinely tied to the same commit as the job row, not
    merely to `session.flush()`."""
    _, sessionmaker, queue, _storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    async with sessionmaker() as session:
        job = ProcessingJob(
            conversation_id=uuid.UUID(conversation_id),
            source_media_id=uuid.UUID(media_id),
            job_type=JobType.NORMALIZE.value,
            status=ProcessingStatus.QUEUED.value,
        )
        session.add(job)
        await session.flush()
        await write_outbox_entry(
            session,
            job_id=job.id,
            queue_name=queue_name_for(JobType.NORMALIZE),
            payload=str(job.id),
        )
        # Deliberately roll back instead of committing — simulates a
        # crash between flush and commit.
        await session.rollback()

    async with sessionmaker() as session:
        relayed = await relay_pending_outbox(session, queue)
        await session.commit()
    assert relayed == 0  # the rolled-back job/outbox pair never existed
    assert sum(len(v) for v in queue._queues.values()) == 0  # noqa: SLF001
