"""Real tests for the Retention Cleanup Worker (Phase 11, spec §56/§57).

Process Rule 7 mandates over-testing this specific feature more than
anything else in the phase, and never testing destructive deletion logic
against anything except throwaway/synthetic test data created in THIS
session. Every conversation/media/transcript row below is created fresh
by this test file's own fixtures (tests/operations/conftest.py) — real
SQLite rows, real bytes on a real temp-directory filesystem via the
genuine `LocalFilesystemStorage` provider — never a shared/production
fixture, never a mock.
"""

from __future__ import annotations

from app.media.models import MediaAsset, MediaKind
from app.operations.models import RetentionCleanupItem, RetentionCleanupRun
from app.operations.retention_service import run_retention_cleanup
from app.transcription.models import Transcript, TranscriptSegment
from sqlalchemy import select

from tests.operations.conftest import (
    attach_media_asset,
    attach_transcript,
    make_conversation,
    make_organization,
    make_retention_policy,
)


async def test_dry_run_deletes_nothing_but_records_what_would_be_deleted(db_session, storage):
    org = await make_organization(db_session)
    policy = await make_retention_policy(
        db_session, retention_days=0, delete_source_media=True, delete_transcript=True
    )
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=5)
    asset = await attach_media_asset(db_session, storage, conv)
    transcript = await attach_transcript(db_session, conv, asset)
    await db_session.commit()

    run = await run_retention_cleanup(
        db_session, storage, dry_run=True, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.dry_run is True
    assert run.status == "succeeded"
    assert run.items_deleted == 2  # source_media_deleted + transcript_deleted
    assert run.bytes_freed == asset.size_bytes

    # Real filesystem bytes are still there.
    assert await storage.exists(asset.storage_key)
    # DB rows are untouched.
    refreshed_asset = await db_session.get(MediaAsset, asset.id)
    assert refreshed_asset.deleted_at is None
    refreshed_transcript = await db_session.get(Transcript, transcript.id)
    assert refreshed_transcript is not None

    items = (
        (
            await db_session.execute(
                select(RetentionCleanupItem).where(RetentionCleanupItem.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    assert {i.action for i in items} == {"source_media_deleted", "transcript_deleted"}
    for item in items:
        assert "retention_days=0" in item.reason


async def test_execute_zero_retention_deletes_audio_and_transcript_for_real(db_session, storage):
    """The "zero retention" pattern from the spec: Audio -> Processing ->
    Document -> Audio DELETE -> Transcript DELETE. retention_days=0 means
    the very next cleanup run after the conversation exists is eligible."""
    org = await make_organization(db_session)
    policy = await make_retention_policy(
        db_session,
        retention_days=0,
        delete_source_media=True,
        delete_derived_media=True,
        delete_transcript=True,
    )
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=1)
    source_asset = await attach_media_asset(
        db_session, storage, conv, kind=MediaKind.SOURCE_AUDIO.value
    )
    derived_asset = await attach_media_asset(
        db_session, storage, conv, kind=MediaKind.NORMALIZED_AUDIO.value
    )
    transcript = await attach_transcript(db_session, conv, source_asset, segment_count=4)
    await db_session.commit()

    source_key = source_asset.storage_key
    derived_key = derived_asset.storage_key
    assert await storage.exists(source_key)
    assert await storage.exists(derived_key)

    run = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.dry_run is False
    assert run.status == "succeeded"
    assert run.items_deleted == 3  # source + derived + transcript

    # Bytes are genuinely gone from the filesystem.
    assert not await storage.exists(source_key)
    assert not await storage.exists(derived_key)

    # MediaAsset rows remain as tombstones (provenance), but tombstoned.
    refreshed_source = await db_session.get(MediaAsset, source_asset.id)
    refreshed_derived = await db_session.get(MediaAsset, derived_asset.id)
    assert refreshed_source.deleted_at is not None
    assert refreshed_derived.deleted_at is not None

    # Transcript row (and, via ON DELETE CASCADE, its segments) is
    # genuinely gone — not soft-deleted, not blanked in place.
    assert await db_session.get(Transcript, transcript.id) is None
    remaining_segments = (
        (
            await db_session.execute(
                select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining_segments == []


async def test_conversation_younger_than_threshold_is_untouched(db_session, storage):
    org = await make_organization(db_session)
    policy = await make_retention_policy(db_session, retention_days=30, delete_source_media=True)
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=5)
    asset = await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    run = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.items_deleted == 0
    assert await storage.exists(asset.storage_key)
    refreshed = await db_session.get(MediaAsset, asset.id)
    assert refreshed.deleted_at is None


async def test_conversation_with_keep_indefinitely_policy_is_never_touched(db_session, storage):
    """retention_days=None ("keep indefinitely") must never be picked up
    by the worker's policy query, no matter how old the conversation is."""
    org = await make_organization(db_session)
    policy = await make_retention_policy(db_session, retention_days=None, delete_source_media=True)
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=99999)
    asset = await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    run = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.items_deleted == 0
    assert await storage.exists(asset.storage_key)


async def test_conversation_with_no_policy_is_never_touched(db_session, storage):
    org = await make_organization(db_session)
    # A second, unrelated aggressive policy exists in the DB — it must
    # never affect a conversation that isn't assigned to it.
    await make_retention_policy(db_session, retention_days=0, delete_source_media=True)
    conv = await make_conversation(db_session, org, retention_policy=None, age_days=99999)
    asset = await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    run = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.items_deleted == 0
    assert await storage.exists(asset.storage_key)


async def test_inactive_policy_is_never_enforced(db_session, storage):
    org = await make_organization(db_session)
    policy = await make_retention_policy(
        db_session, retention_days=0, delete_source_media=True, active=False
    )
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=30)
    asset = await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    run = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()

    assert run.items_deleted == 0
    assert await storage.exists(asset.storage_key)


async def test_already_deleted_asset_is_never_deleted_twice(db_session, storage):
    """Idempotency: a second cleanup run must not try to delete bytes
    that a prior run already removed (and must not double-count them)."""
    org = await make_organization(db_session)
    policy = await make_retention_policy(db_session, retention_days=0, delete_source_media=True)
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=1)
    await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    first = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()
    assert first.items_deleted == 1

    second = await run_retention_cleanup(
        db_session, storage, dry_run=False, triggered_by_user_id=None
    )
    await db_session.commit()
    assert second.items_deleted == 0


async def test_only_conversations_matching_policy_are_affected(db_session, storage):
    """A conversation under a *different* org/policy that happens to also
    be old must be unaffected by a run that only matches one policy's
    conversations — proves the WHERE clause is scoped per-policy, not a
    blanket sweep."""
    org = await make_organization(db_session)
    aggressive = await make_retention_policy(db_session, retention_days=0, delete_source_media=True)
    lenient = await make_retention_policy(db_session, retention_days=3650, delete_source_media=True)

    old_conv = await make_conversation(db_session, org, retention_policy=aggressive, age_days=10)
    old_asset = await attach_media_asset(db_session, storage, old_conv)

    protected_conv = await make_conversation(db_session, org, retention_policy=lenient, age_days=10)
    protected_asset = await attach_media_asset(db_session, storage, protected_conv)
    await db_session.commit()

    run = await run_retention_cleanup(db_session, storage, dry_run=False, triggered_by_user_id=None)
    await db_session.commit()

    assert run.items_deleted == 1
    assert not await storage.exists(old_asset.storage_key)
    assert await storage.exists(protected_asset.storage_key)


async def test_run_and_items_are_queryable_after_commit(db_session, storage):
    org = await make_organization(db_session)
    policy = await make_retention_policy(db_session, retention_days=0, delete_source_media=True)
    conv = await make_conversation(db_session, org, retention_policy=policy, age_days=1)
    await attach_media_asset(db_session, storage, conv)
    await db_session.commit()

    run = await run_retention_cleanup(db_session, storage, dry_run=False, triggered_by_user_id=None)
    await db_session.commit()

    fetched = await db_session.get(RetentionCleanupRun, run.id)
    assert fetched is not None
    assert fetched.completed_at is not None
    # SQLite's server_default now() (started_at) returns a naive datetime
    # while completed_at is set explicitly as tz-aware UTC — normalize
    # before comparing (a Postgres deployment stores both consistently
    # tz-aware; this is purely a SQLite-test-driver quirk).
    started = fetched.started_at
    if started.tzinfo is None:
        from datetime import UTC

        started = started.replace(tzinfo=UTC)
    assert started <= fetched.completed_at
