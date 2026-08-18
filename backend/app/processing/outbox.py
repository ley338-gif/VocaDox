"""Transactional Outbox relay (Phase 3.1 hardening).

`write_outbox_entry` is called by app.processing.service instead of
calling `QueueBackend.enqueue()` directly, from inside the same
not-yet-committed transaction as the ProcessingJob row it announces — see
`app.processing.models.OutboxStatus` for the full rationale and the exact
dual-write race this closes.

`relay_pending_outbox` is the other half: it atomically claims PENDING
rows (a single `UPDATE ... WHERE status = 'pending' RETURNING ...`, which
is dialect-portable across Postgres and SQLite and requires no
backend-specific row-locking clause such as `FOR UPDATE SKIP LOCKED`),
publishes each to Valkey, and only then lets the caller commit. Every
`ProcessingWorker`'s maintenance sweep calls this on every loop iteration
(default every ~5s, bounded by the dequeue poll timeout), so a job
created via the API — or chained by a worker's own success handler — is
never left waiting on Valkey longer than one sweep interval, regardless
of whether the process that created it crashed immediately afterward.

Delivery is at-least-once, never zero-times: if the process crashes after
`queue.enqueue()` succeeds but before this function's caller commits, the
UPDATE rolls back with everything else in that transaction, the row is
still PENDING, and the next sweep republishes it — a safe duplicate (see
OutboxStatus's docstring for why a second delivery of the same job id is
always a no-op).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.valkey.backends import QueueBackend
from app.processing.models import OutboxStatus, ProcessingOutbox

logger = logging.getLogger("vocadox.processing.outbox")

_RELAY_BATCH_SIZE = 200


async def write_outbox_entry(
    session: AsyncSession, *, job_id: uuid.UUID, queue_name: str, payload: str
) -> None:
    """Flushes (never commits) a PENDING outbox row. Must be called in the
    same transaction as the ProcessingJob row it announces — the caller's
    eventual `session.commit()` makes both durable atomically, or neither
    happens at all."""
    session.add(
        ProcessingOutbox(job_id=job_id, queue_name=queue_name, payload=payload)
    )
    await session.flush()


async def relay_pending_outbox(session: AsyncSession, queue: QueueBackend) -> int:
    """Publishes up to `_RELAY_BATCH_SIZE` PENDING outbox rows to Valkey and
    marks them PUBLISHED, all inside the caller's transaction (caller must
    still call `session.commit()` — this function only flushes). Returns
    the number of rows relayed. Safe to call from multiple concurrent
    worker processes: the claiming UPDATE only affects rows still PENDING
    at execution time, so two relayers racing on the same row simply have
    one of them affect 0 rows for it (whichever commits second finds
    nothing left to claim — this module never uses SELECT ... FOR UPDATE,
    intentionally, so it also works against the SQLite backend the test
    suite uses)."""
    candidate_ids = (
        (
            await session.execute(
                select(ProcessingOutbox.id)
                .where(ProcessingOutbox.status == OutboxStatus.PENDING.value)
                .order_by(ProcessingOutbox.created_at)
                .limit(_RELAY_BATCH_SIZE)
            )
        )
        .scalars()
        .all()
    )
    if not candidate_ids:
        return 0

    claimed_result = await session.execute(
        update(ProcessingOutbox)
        .where(
            ProcessingOutbox.id.in_(candidate_ids),
            ProcessingOutbox.status == OutboxStatus.PENDING.value,
        )
        .values(status=OutboxStatus.PUBLISHED.value, published_at=datetime.now(UTC))
        .returning(ProcessingOutbox.id, ProcessingOutbox.queue_name, ProcessingOutbox.payload)
    )
    claimed_rows = claimed_result.all()
    await session.flush()

    for _row_id, queue_name, payload in claimed_rows:
        try:
            await queue.enqueue(queue_name, payload)
        except Exception:
            # Never let one bad message block the rest of the batch or
            # crash the sweep — but this row is now marked PUBLISHED in
            # the still-open transaction. Roll the whole relay batch back
            # so it reverts to PENDING and is retried next sweep, rather
            # than silently losing the message (spec: "must not
            # permanently orphan a processing job").
            logger.exception(
                "outbox relay: queue.enqueue failed, rolling back this relay batch",
                extra={"queue_name": queue_name},
            )
            raise

    return len(claimed_rows)
