"""Backup and Restore (Phase 11, spec §64).

Covers exactly the two things the spec calls out: PostgreSQL (a full
`pg_dump` — every relational table: Documents, retained Transcripts,
Templates, Profiles, Configuration, RetentionPolicy rows, everything) and
retained Media (a filesystem archive of `media_storage_root`, separate
from `model_volume_root` — models are Phase 3.1's concern, not backed up
here, matching that ADR's "don't mix model files with Conversation
media" principle).

Architecture decision — CREATE is an admin HTTP action, RESTORE is
CLI-only:

`create_backup` is safe to expose over HTTP (`backup:trigger`) because
`pg_dump` takes an internally-consistent snapshot without blocking
concurrent reads/writes and without touching the running application's
own state — an admin can trigger it, keep using the app, and get a real
artifact back.

`restore_backup` is NOT exposed over HTTP. Restoring genuinely overwrites
the target database's data and the target media directory's files — an
operation that should never be one accidental click away, and one an
in-process request handler cannot safely perform on ITS OWN database
connection pool anyway (pg_restore needs its own connection, and every
other request against the same pool would see a half-restored database
mid-operation). It is a `python -m app.cli.backup restore <backup_dir>`
operator-run procedure instead, documented in
docs/operations/disaster-recovery.md — the same shape as Phase 3.1's
`model-manager` CLI ("administrator-facing entrypoint", not a button).
"""

from __future__ import annotations

import asyncio
import shutil
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.models import BackupRecord, BackupStatus


class BackupError(RuntimeError):
    """Raised when a backup or restore step fails. `stderr` carries the
    real subprocess output for operator diagnosis — never swallowed."""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def to_libpq_url(database_url: str) -> str:
    """`postgresql+asyncpg://...` -> `postgresql://...` — pg_dump/pg_restore/
    psql speak libpq connection strings, not SQLAlchemy driver URLs."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _run_subprocess(*args: str) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        # Binary not found / not executable — surfaced as a BackupError
        # (never a raw OSError) so every caller's `except BackupError`
        # handles it uniformly, and the BackupRecord still gets marked
        # FAILED with a real error message instead of crashing the request.
        raise BackupError(f"failed to start {args[0]}: {exc}") from exc
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise BackupError(
            f"command failed (exit {process.returncode}): {' '.join(args[:1])}",
            stderr=stderr.decode(errors="replace"),
        )


def _directory_size_and_count(root: Path) -> tuple[int, int]:
    total_bytes = 0
    count = 0
    if not root.exists():
        return 0, 0
    for path in root.rglob("*"):
        if path.is_file():
            total_bytes += path.stat().st_size
            count += 1
    return total_bytes, count


async def create_backup(
    session: AsyncSession,
    *,
    backup_root: str,
    database_url: str,
    media_storage_root: str,
    pg_dump_path: str,
    triggered_by_user_id: uuid.UUID | None,
) -> BackupRecord:
    """Runs a real `pg_dump` (custom format, includes full schema + data —
    a target restored from this dump needs no prior `alembic upgrade
    head`) and a real tar archive of the media storage root. Writes both
    into `<backup_root>/<record.id>/`. Never deletes or mutates the
    source data it reads from."""
    record = BackupRecord(
        status=BackupStatus.RUNNING.value,
        storage_path="",  # filled in below once record.id is assigned by flush()
        triggered_by_user_id=triggered_by_user_id,
    )
    session.add(record)
    await session.flush()
    # The backup's own directory is named after its record id for easy
    # operator correlation (admin UI shows the id; the id IS the dirname).
    dest_dir = Path(backup_root) / str(record.id)
    record.storage_path = str(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        dump_path = dest_dir / "database.dump"
        await _run_subprocess(
            pg_dump_path,
            f"--dbname={to_libpq_url(database_url)}",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={dump_path}",
        )
        record.database_dump_bytes = dump_path.stat().st_size

        media_root = Path(media_storage_root)
        media_bytes, media_files = _directory_size_and_count(media_root)
        archive_path = dest_dir / "media.tar"
        if media_root.exists():
            # Synchronous tar creation on a background thread — real media
            # volumes can be large; never block the event loop.
            await asyncio.to_thread(_create_media_tar, media_root, archive_path)
            record.media_archive_bytes = archive_path.stat().st_size
        else:
            record.media_archive_bytes = 0
        record.media_file_count = media_files

        record.status = BackupStatus.SUCCEEDED.value
    except Exception as exc:  # noqa: BLE001 - the record must capture failure, never crash silently
        record.status = BackupStatus.FAILED.value
        record.error_message = (
            f"{exc}\n{exc.stderr}"[:2048] if isinstance(exc, BackupError) else str(exc)[:2048]
        )
        raise
    finally:
        record.completed_at = datetime.now(UTC)
        await session.flush()

    return record


def _create_media_tar(media_root: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w") as tar:
        tar.add(media_root, arcname=".")


def restore_backup(
    *,
    backup_dir: str,
    database_url: str,
    media_storage_root: str,
    pg_restore_path: str,
) -> None:
    """Synchronous, standalone (no AsyncSession — see module docstring for
    why this is CLI-only). Restores the database via `pg_restore --clean`
    (drops/recreates every object the dump describes before recreating it
    — the target database must exist and be reachable, but its prior
    contents are NOT preserved) and extracts the media tar over
    `media_storage_root`."""
    import subprocess

    backup_path = Path(backup_dir)
    dump_path = backup_path / "database.dump"
    archive_path = backup_path / "media.tar"
    if not dump_path.exists():
        raise BackupError(f"no database.dump found under {backup_dir}")

    try:
        result = subprocess.run(  # noqa: S603 - operator-invoked CLI, trusted local paths/binaries
            [
                pg_restore_path,
                f"--dbname={to_libpq_url(database_url)}",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                str(dump_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise BackupError(f"failed to start {pg_restore_path}: {exc}") from exc
    if result.returncode != 0:
        raise BackupError("pg_restore failed", stderr=result.stderr)

    if archive_path.exists():
        media_root = Path(media_storage_root)
        # Restore is destructive by design: the target media root is
        # cleared before extraction so a restore always yields exactly
        # the backed-up state, never a mix of old and restored files.
        if media_root.exists():
            shutil.rmtree(media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r") as tar:
            tar.extractall(media_root, filter="data")  # noqa: S202 - trusted, operator-supplied backup
