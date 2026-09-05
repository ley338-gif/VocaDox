"""`python -m app.cli.retention_cleanup` — the automated Retention Cleanup
Worker entrypoint (Phase 11, spec §56/§57), meant to be run on a schedule
(host cron, a Kubernetes CronJob, `docker compose run --rm
retention-cleanup`, ...) independent of whether an admin ever opens the
UI.

Safe by default: **dry-run unless `--execute` is passed.** This mirrors
the admin HTTP endpoint's default (`POST /admin/operations/
retention-cleanup/run` defaults its own `dry_run` field to `true`) — see
app.operations.retention_service's module docstring for the full set of
safety rules this feature hard-codes.

    python -m app.cli.retention_cleanup run            # dry run (default, safe)
    python -m app.cli.retention_cleanup run --execute   # REAL, IRREVERSIBLE deletion
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.storage import get_storage_provider
from app.operations.retention_service import run_retention_cleanup
from app.platform.config import get_settings
from app.platform.db import model_registry  # noqa: F401 - registers all domain models
from app.platform.db.session import get_sessionmaker


async def _run(*, execute: bool) -> int:
    settings = get_settings()
    storage = get_storage_provider()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        run = await run_retention_cleanup(
            session,
            storage,
            dry_run=not execute,
            triggered_by_user_id=None,
            batch_size=settings.retention_cleanup_batch_size,
        )
        await session.commit()
    mode = "EXECUTED (real deletions)" if execute else "DRY RUN (nothing deleted)"
    print(f"Retention cleanup run {run.id}: {mode}")
    print(f"  conversations evaluated: {run.conversations_evaluated}")
    print(f"  items {'deleted' if execute else 'that would be deleted'}: {run.items_deleted}")
    print(f"  bytes {'freed' if execute else 'that would be freed'}: {run.bytes_freed}")
    return 0 if run.status == "succeeded" else 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="retention-cleanup", description="VocaDox retention cleanup worker."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Evaluate retention policies.")
    run_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually perform deletions. Without this flag, runs in dry-run mode "
        "(evaluates and records what WOULD be deleted, deletes nothing).",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return asyncio.run(_run(execute=args.execute))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
