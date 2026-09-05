"""Fixtures for Phase 11 Operations tests.

`db_session` is a real SQLite (aiosqlite) in-memory database — not a mock
— built from the exact same `Base.metadata` every other domain's tests
use (see tests/conversations/conftest.py's `app_env` fixture for the
same pattern). `storage` is the REAL `LocalFilesystemStorage` provider
(never a fake) writing to a real temp directory, so "physically deleted"
assertions in test_retention_service.py check real bytes on a real
filesystem, not a mock's call log.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from app.conversations.models import Conversation, ConversationStatus, RetentionPolicy
from app.media.models import MediaAsset, MediaKind, MediaSourceType
from app.organizations.models import Organization
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import Base
from app.processing.models import ProcessingRun, RunStatus, RunType
from app.providers.storage import LocalFilesystemStorage
from app.transcription.models import Transcript, TranscriptSegment, TranscriptStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # SQLite doesn't enforce FK ondelete=CASCADE unless explicitly turned
    # on — turn it on so the real-physical-deletion cascade assertions
    # (Transcript -> TranscriptSegment) genuinely exercise the same
    # ON DELETE CASCADE behavior Postgres enforces in production.
    from sqlalchemy import event

    def _enable_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine.sync_engine, "connect", _enable_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
def storage(tmp_path) -> LocalFilesystemStorage:
    return LocalFilesystemStorage(tmp_path / "media")


async def make_organization(session: AsyncSession) -> Organization:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    return org


async def make_retention_policy(
    session: AsyncSession,
    *,
    retention_days: int | None,
    delete_source_media: bool = False,
    delete_derived_media: bool = False,
    delete_transcript: bool = False,
    active: bool = True,
    name: str | None = None,
) -> RetentionPolicy:
    policy = RetentionPolicy(
        name=name or f"policy-{uuid.uuid4().hex[:8]}",
        retention_days=retention_days,
        delete_source_media=delete_source_media,
        delete_derived_media=delete_derived_media,
        delete_transcript=delete_transcript,
        active=active,
    )
    session.add(policy)
    await session.flush()
    return policy


async def make_conversation(
    session: AsyncSession,
    org: Organization,
    *,
    retention_policy: RetentionPolicy | None,
    age_days: int,
) -> Conversation:
    started_at = datetime.now(UTC) - timedelta(days=age_days)
    conv = Conversation(
        organization_id=org.id,
        title=f"Conversation {uuid.uuid4().hex[:6]}",
        status=ConversationStatus.READY.value,
        started_at=started_at,
        retention_policy_id=retention_policy.id if retention_policy else None,
    )
    session.add(conv)
    await session.flush()
    return conv


async def attach_media_asset(
    session: AsyncSession,
    storage: LocalFilesystemStorage,
    conversation: Conversation,
    *,
    kind: str = MediaKind.SOURCE_AUDIO.value,
    content: bytes = b"synthetic-audio-bytes-not-a-real-recording",
) -> MediaAsset:
    storage_key = await storage.save(content, suffix=".bin")
    asset = MediaAsset(
        conversation_id=conversation.id,
        kind=kind,
        source_type=MediaSourceType.FILE_UPLOAD.value,
        storage_key=storage_key,
        content_type="application/octet-stream",
        size_bytes=len(content),
        sha256="0" * 64,
    )
    session.add(asset)
    await session.flush()
    return asset


async def attach_transcript(
    session: AsyncSession,
    conversation: Conversation,
    source_media: MediaAsset,
    *,
    segment_count: int = 3,
) -> Transcript:
    run = ProcessingRun(
        conversation_id=conversation.id,
        source_media_id=source_media.id,
        run_type=RunType.SPEECH_TO_TEXT.value,
        status=RunStatus.SUCCEEDED.value,
        provider="fake",
        model="fake-model",
        application_version="test",
    )
    session.add(run)
    await session.flush()

    transcript = Transcript(
        conversation_id=conversation.id,
        source_media_id=source_media.id,
        processing_run_id=run.id,
        status=TranscriptStatus.READY.value,
        provider="fake",
        model="fake-model",
    )
    session.add(transcript)
    await session.flush()

    for i in range(segment_count):
        session.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                sequence=i,
                start_ms=i * 1000,
                end_ms=(i + 1) * 1000,
                original_text=f"synthetic segment {i} — not real patient/participant speech",
            )
        )
    await session.flush()
    return transcript
