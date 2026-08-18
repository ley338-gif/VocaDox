"""Worker process entrypoint: `python -m app.workers.runner --role speech`
or `--role diarization`. This is what `deploy/docker-compose.yml`'s
`worker-speech`/`worker-diarization` containers run.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import uuid

from app.platform.db import model_registry  # noqa: F401 - registers all domain models; see below
from app.platform.logging import configure_logging
from app.processing.queues import DIARIZATION_WORKER_JOB_TYPES, SPEECH_WORKER_JOB_TYPES
from app.workers.processing_worker import run_worker

# The import above is not decorative: unlike app.core.app_factory (which
# imports model_registry before the API ever serves a request), nothing
# else on the worker's code path touched every domain's models module
# before SQLAlchemy resolves a cross-domain relationship/FK lazily.
# Found by real testing (fresh `docker compose up` + real worker
# containers, not just pytest's SQLite-metadata setup, which happens to
# import model_registry itself in every test conftest.py) —
# `NoReferencedTableError: ... could not find table 'organizations'`
# the first time a worker touched a Conversation-adjacent query, because
# app.organizations.models had never been imported in that process.

logger = logging.getLogger("vocadox.worker.runner")


def _worker_id(role: str) -> str:
    return f"{role}-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


async def _main() -> None:
    parser = argparse.ArgumentParser(description="VocaDox processing worker")
    parser.add_argument("--role", choices=["speech", "diarization"], required=True)
    args = parser.parse_args()

    from app.platform.config import get_settings

    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    job_types = SPEECH_WORKER_JOB_TYPES if args.role == "speech" else DIARIZATION_WORKER_JOB_TYPES
    worker_id = _worker_id(args.role)
    logger.info("starting worker", extra={"worker_id": worker_id, "role": args.role})
    await run_worker(worker_id=worker_id, job_types=job_types)


if __name__ == "__main__":
    asyncio.run(_main())
