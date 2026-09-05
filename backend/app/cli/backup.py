"""`python -m app.cli.backup` — the administrator-facing entrypoint for
creating and restoring backups (Phase 11, spec §64).

    python -m app.cli.backup create
    python -m app.cli.backup list
    python -m app.cli.backup restore <backup_dir_or_id>

`create`/`list` also exist as admin HTTP endpoints (`POST`/`GET
/admin/operations/backups`, gated by `backup:trigger`/`operations:read`)
for convenience — this CLI is the ONLY way to restore (see
app.operations.backup_service's module docstring for why restore is
deliberately not an HTTP endpoint), and is also the documented
disaster-recovery path when the application itself cannot be relied on
(e.g. the database is unreachable) — see
docs/operations/disaster-recovery.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.operations.backup_service import BackupError, create_backup, restore_backup
from app.platform.config import get_settings
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import get_sessionmaker


async def _create() -> int:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            record = await create_backup(
                session,
                backup_root=settings.backup_root,
                database_url=settings.database_url,
                media_storage_root=settings.media_storage_root,
                pg_dump_path=settings.pg_dump_path,
                triggered_by_user_id=None,
            )
            await session.commit()
        except BackupError as exc:
            await session.commit()  # persist the FAILED record for the audit trail
            print(f"Backup failed: {exc}\n{exc.stderr}", file=sys.stderr)
            return 1
        print(f"Backup {record.id} succeeded: {record.storage_path}")
        print(
            f"  database.dump: {record.database_dump_bytes} bytes, "
            f"media.tar: {record.media_archive_bytes} bytes "
            f"({record.media_file_count} files)"
        )
        return 0


async def _list() -> int:
    from sqlalchemy import select

    from app.operations.models import BackupRecord

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            select(BackupRecord).order_by(BackupRecord.started_at.desc())
        )
        for record in result.scalars().all():
            print(
                f"{record.id}  {record.status:10}  {record.started_at}  {record.storage_path}"
            )
    return 0


def _restore(backup_dir: str) -> int:
    settings = get_settings()
    resolved = Path(backup_dir)
    if not resolved.is_absolute() and not resolved.exists():
        # Allow passing just the backup id, resolved under backup_root.
        resolved = Path(settings.backup_root) / backup_dir
    try:
        restore_backup(
            backup_dir=str(resolved),
            database_url=settings.database_url,
            media_storage_root=settings.media_storage_root,
            pg_restore_path=settings.pg_restore_path,
        )
    except BackupError as exc:
        print(f"Restore failed: {exc}\n{exc.stderr}", file=sys.stderr)
        return 1
    print(f"Restore from {resolved} succeeded.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="backup", description="VocaDox backup/restore CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create", help="Create a real backup (pg_dump + media tar).")
    subparsers.add_parser("list", help="List backup records.")
    restore_parser = subparsers.add_parser(
        "restore", help="Restore a backup. DESTRUCTIVE — overwrites the target database/media."
    )
    restore_parser.add_argument("backup_dir", help="Backup directory path or backup id.")

    args = parser.parse_args(argv)
    if args.command == "create":
        return asyncio.run(_create())
    if args.command == "list":
        return asyncio.run(_list())
    if args.command == "restore":
        return _restore(args.backup_dir)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
