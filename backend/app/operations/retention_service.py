"""The real Retention Cleanup Worker (Phase 11, spec §56/§57).

`RetentionPolicy` (Phase 2 model, Phase 7 admin CRUD) has existed since
Phase 2 with explicit "no automated enforcement yet" noted every phase
since. This module is that enforcement, finally.

Safety rules this module hard-codes (see the phase brief's Process Rule
7 — this feature performs real, irreversible deletion of user data):

1. `run_retention_cleanup`'s `dry_run` parameter has NO default here —
   every caller (router, CLI) must pass it explicitly, so "what mode did
   this run actually execute in" is never accidental. Both call sites
   (router, CLI) default their OWN parameter to `dry_run=True`.
2. In dry-run mode, NOTHING is deleted — the exact same evaluation logic
   runs, producing the exact same `RetentionCleanupItem` rows describing
   what WOULD be deleted, but `storage.delete(...)` and the SQL DELETE
   are never called. `RetentionCleanupRun.dry_run` records which mode
   actually ran.
3. Every individual deletion is a separate, auditable
   `RetentionCleanupItem` row recorded BEFORE the physical action is
   taken, with `reason` stating exactly which policy and threshold
   triggered it, never the deleted content itself.
4. Physical media deletion is bytes-first: `storage.delete(storage_key)`
   is called (and only on success is `MediaAsset.deleted_at` set) — a
   MediaAsset row is a tombstone (kept for provenance) with its bytes
   genuinely gone, never a "deleted_at flip" alone (see
   docs/architecture/adr/0015-retention-and-deletion-semantics.md and the
   phase brief: "a soft-deleted DB record with the audio still on disk
   is NOT deleted from a privacy perspective").
5. Transcript deletion is a genuine SQL DELETE of the `Transcript` row —
   `TranscriptSegment`/`TranscriptSegmentCorrection` cascade at the
   database FK level (`ondelete="CASCADE"`, already declared on those
   models since Phase 3) — the segment text is truly gone, not blanked
   in place and not merely flagged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.conversations.models import Conversation, RetentionPolicy
from app.media.models import MediaKind
from app.operations.models import RetentionCleanupItem, RetentionCleanupRun
from app.providers.storage import StorageProvider
from app.transcription.models import Transcript

_DERIVED_MEDIA_KINDS = (MediaKind.NORMALIZED_AUDIO.value, MediaKind.ATTACHMENT.value)


async def run_retention_cleanup(
    session: AsyncSession,
    storage: StorageProvider,
    *,
    dry_run: bool,
    triggered_by_user_id: uuid.UUID | None,
    batch_size: int = 500,
    now: datetime | None = None,
) -> RetentionCleanupRun:
    """Evaluate every active `RetentionPolicy` with a real `retention_days`
    threshold against the conversations assigned to it, and (unless
    `dry_run`) physically delete whatever the policy's flags say to
    delete once a conversation's age passes that threshold.

    Age is computed from `conversation.started_at` if set, else
    `conversation.created_at` — the closest real timestamp this codebase
    has to "when the recorded event happened" (see
    app.conversations.models.Conversation). A conversation whose
    retention_policy_id is NULL, or points at an inactive policy, or at a
    policy with `retention_days=None` ("keep indefinitely"), is never
    touched by this worker.
    """
    now = now or datetime.now(UTC)
    run = RetentionCleanupRun(
        dry_run=dry_run, status="running", triggered_by_user_id=triggered_by_user_id
    )
    session.add(run)
    await session.flush()

    conversations_evaluated = 0
    items_deleted = 0
    bytes_freed = 0

    try:
        policy_stmt = select(RetentionPolicy).where(
            RetentionPolicy.active.is_(True), RetentionPolicy.retention_days.is_not(None)
        )
        policies = list((await session.execute(policy_stmt)).scalars().all())

        for policy in policies:
            assert policy.retention_days is not None  # narrowed by the WHERE clause above
            conv_stmt = (
                select(Conversation)
                .where(
                    Conversation.retention_policy_id == policy.id,
                    Conversation.deleted_at.is_(None),
                )
                .options(selectinload(Conversation.media_assets))
                .limit(batch_size)
            )
            conversations = list((await session.execute(conv_stmt)).scalars().all())

            for conversation in conversations:
                conversations_evaluated += 1
                reference_time = conversation.started_at or conversation.created_at
                if reference_time.tzinfo is None:
                    reference_time = reference_time.replace(tzinfo=UTC)
                age_days = (now - reference_time).days
                if age_days < policy.retention_days:
                    continue
                reason = (
                    f"age_days={age_days} >= retention_days={policy.retention_days} "
                    f"(policy '{policy.name}', id={policy.id})"
                )

                if policy.delete_source_media:
                    freed, deleted_count = await _delete_media(
                        session,
                        storage,
                        conversation=conversation,
                        run=run,
                        policy=policy,
                        kinds=(MediaKind.SOURCE_AUDIO.value,),
                        action="source_media_deleted",
                        reason=reason,
                        dry_run=dry_run,
                    )
                    items_deleted += deleted_count
                    bytes_freed += freed

                if policy.delete_derived_media:
                    freed, deleted_count = await _delete_media(
                        session,
                        storage,
                        conversation=conversation,
                        run=run,
                        policy=policy,
                        kinds=_DERIVED_MEDIA_KINDS,
                        action="derived_media_deleted",
                        reason=reason,
                        dry_run=dry_run,
                    )
                    items_deleted += deleted_count
                    bytes_freed += freed

                if policy.delete_transcript:
                    deleted_count = await _delete_transcripts(
                        session,
                        conversation=conversation,
                        run=run,
                        policy=policy,
                        reason=reason,
                        dry_run=dry_run,
                    )
                    items_deleted += deleted_count

        run.status = "succeeded"
    except Exception as exc:  # noqa: BLE001 - the run row must record failure, never crash silently
        run.status = "failed"
        run.error_message = str(exc)[:2048]
        raise
    finally:
        run.conversations_evaluated = conversations_evaluated
        run.items_deleted = items_deleted
        run.bytes_freed = bytes_freed
        run.completed_at = datetime.now(UTC)
        await session.flush()

    return run


async def _delete_media(
    session: AsyncSession,
    storage: StorageProvider,
    *,
    conversation: Conversation,
    run: RetentionCleanupRun,
    policy: RetentionPolicy,
    kinds: tuple[str, ...],
    action: str,
    reason: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Returns (bytes_freed, items_recorded). Every eligible asset gets its
    own `RetentionCleanupItem` row and, unless `dry_run`, is genuinely
    unlinked from storage before its `deleted_at` tombstone is set."""
    bytes_freed = 0
    items_recorded = 0
    for asset in conversation.media_assets:
        if asset.kind not in kinds or asset.deleted_at is not None:
            continue
        item = RetentionCleanupItem(
            run_id=run.id,
            conversation_id=conversation.id,
            retention_policy_id=policy.id,
            action=action,
            media_asset_id=asset.id,
            bytes_freed=asset.size_bytes,
            reason=reason,
        )
        session.add(item)
        items_recorded += 1
        bytes_freed += asset.size_bytes
        if not dry_run:
            await storage.delete(asset.storage_key)
            asset.deleted_at = datetime.now(UTC)
    return bytes_freed, items_recorded


async def _delete_transcripts(
    session: AsyncSession,
    *,
    conversation: Conversation,
    run: RetentionCleanupRun,
    policy: RetentionPolicy,
    reason: str,
    dry_run: bool,
) -> int:
    transcripts = list(
        (
            await session.execute(
                select(Transcript).where(Transcript.conversation_id == conversation.id)
            )
        )
        .scalars()
        .all()
    )
    items_recorded = 0
    for transcript in transcripts:
        from app.transcription.models import TranscriptSegment

        segment_count_stmt = select(TranscriptSegment).where(
            TranscriptSegment.transcript_id == transcript.id
        )
        segment_count = len((await session.execute(segment_count_stmt)).scalars().all())

        item = RetentionCleanupItem(
            run_id=run.id,
            conversation_id=conversation.id,
            retention_policy_id=policy.id,
            action="transcript_deleted",
            transcript_id=transcript.id,
            segments_deleted=segment_count,
            reason=reason,
        )
        session.add(item)
        items_recorded += 1
        if not dry_run:
            # A genuine SQL DELETE, not a status/deleted_at flag flip —
            # TranscriptSegment/TranscriptSegmentCorrection cascade at the
            # database FK level (ondelete="CASCADE" on both since Phase 3).
            await session.execute(delete(Transcript).where(Transcript.id == transcript.id))
    return items_recorded
