"""SQLAlchemy ORM models for Phase 11 Operations: Backup records and
Retention Cleanup run/item audit trail.

`BackupRecord` is metadata ABOUT a backup artifact (a directory on disk
containing a real `pg_dump` custom-format file plus a tarball of the
media storage root) — never the artifact's bytes themselves.

`RetentionCleanupRun` + `RetentionCleanupItem` are the audit trail spec
Rule 7 requires for this phase's real, automated, irreversible deletion
of user data: enough detail to explain, after the fact, exactly what was
deleted, why (which policy, what threshold), and when — without ever
logging the deleted content itself (only ids, counts, and byte counts).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class BackupStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BackupRecord(Base):
    """One row per backup ATTEMPT (mirrors the Phase 10
    `WebhookDelivery`/Phase 9 audit-trail pattern of "one row per real
    attempt, success or failure, never silently discarded")."""

    __tablename__ = "backup_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BackupStatus.RUNNING.value, index=True
    )
    # Absolute path to the backup's own directory under the configured
    # backup root (`<backup_root>/<id>/`) — contains `database.dump`
    # (pg_dump custom format) and `media.tar` (media storage root).
    # Never returned to non-admin API responses; admins only ever see the
    # `id`, not the raw filesystem path, over HTTP (see schemas.py).
    storage_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    database_dump_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    media_archive_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    media_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetentionCleanupRun(Base):
    """One row per retention-cleanup invocation, whether triggered via the
    admin API, the `vocadox-retention-cleanup` CLI/cron, or a test. `dry_run`
    defaults conceptually to True at every call site above this model
    (see `app.operations.retention_service.run_retention_cleanup`'s
    default) — this row records which mode actually ran, so the audit
    trail itself proves whether real deletions happened."""

    __tablename__ = "retention_cleanup_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    conversations_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_freed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetentionCleanupItem(Base):
    """One row per individual physical deletion (or, in dry-run mode, per
    deletion that WOULD have happened) — the granular "what/why/when"
    audit detail. `reason` is a short, structured, human-readable string
    (e.g. "age_days=45 >= retention_days=30 (policy 'Standard-30')") —
    never conversation/transcript/fact/document content."""

    __tablename__ = "retention_cleanup_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("retention_cleanup_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    retention_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("retention_policies.id", ondelete="SET NULL"), nullable=True
    )
    # "source_media_deleted" | "derived_media_deleted" | "transcript_deleted"
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    bytes_freed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    segments_deleted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
