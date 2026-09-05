"""Phase 7 Admin Portal domain logic: Dashboard aggregation, Jobs/Workers
read-model, Storage usage, and Retention Policy CRUD.

Deliberately reuses existing infrastructure rather than building parallel
systems:
- Dashboard health reuses `app.platform.db.session.check_database_connectivity`
  / `app.platform.valkey.valkey_backend.check_valkey_connectivity` /
  `app.core.ai_providers.get_speech_provider().status()` etc. — the exact
  same checks `app.platform.health` and `app.administration.router`'s
  pre-existing provider-status endpoints already perform.
- Workers status is derived purely from `ProcessingJob` rows already
  written by Phase 3's worker processes — no new worker-registry table
  (spec: "avoid building a hardware inventory platform").
- Retention Policy CRUD operates on `app.conversations.models.RetentionPolicy`,
  which has existed since Phase 2 with no admin UI until now — no new table,
  no automated enforcement scheduler (that remains Phase 11 scope).
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import RetentionPolicy
from app.processing.models import ProcessingJob, ProcessingStatus

# -- Retention Policies -------------------------------------------------


async def list_retention_policies(session: AsyncSession) -> list[RetentionPolicy]:
    result = await session.execute(select(RetentionPolicy).order_by(RetentionPolicy.name))
    return list(result.scalars().all())


async def get_retention_policy(
    session: AsyncSession, policy_id: uuid.UUID
) -> RetentionPolicy | None:
    return await session.get(RetentionPolicy, policy_id)


async def create_retention_policy(
    session: AsyncSession,
    *,
    name: str,
    retention_days: int | None,
    delete_source_media: bool,
    delete_derived_media: bool,
    delete_transcript: bool = False,
    active: bool,
) -> RetentionPolicy:
    policy = RetentionPolicy(
        name=name,
        retention_days=retention_days,
        delete_source_media=delete_source_media,
        delete_derived_media=delete_derived_media,
        delete_transcript=delete_transcript,
        active=active,
    )
    session.add(policy)
    await session.flush()
    return policy


async def update_retention_policy(
    session: AsyncSession,
    policy: RetentionPolicy,
    *,
    name: str | None = None,
    retention_days: int | None = None,
    delete_source_media: bool | None = None,
    delete_derived_media: bool | None = None,
    delete_transcript: bool | None = None,
    active: bool | None = None,
    _fields_set: set[str] | None = None,
) -> RetentionPolicy:
    fields_set = _fields_set or set()
    if name is not None:
        policy.name = name
    if "retention_days" in fields_set:
        policy.retention_days = retention_days
    if delete_source_media is not None:
        policy.delete_source_media = delete_source_media
    if delete_derived_media is not None:
        policy.delete_derived_media = delete_derived_media
    if delete_transcript is not None:
        policy.delete_transcript = delete_transcript
    if active is not None:
        policy.active = active
    await session.flush()
    return policy


# -- Jobs -----------------------------------------------------------------


async def list_jobs(
    session: AsyncSession,
    *,
    status_filter: str | None = None,
    job_type_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ProcessingJob]:
    stmt = select(ProcessingJob).order_by(ProcessingJob.queued_at.desc())
    if status_filter is not None:
        stmt = stmt.where(ProcessingJob.status == status_filter)
    if job_type_filter is not None:
        stmt = stmt.where(ProcessingJob.job_type == job_type_filter)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_jobs(
    session: AsyncSession, *, status_filter: str | None = None, job_type_filter: str | None = None
) -> int:
    stmt = select(func.count()).select_from(ProcessingJob)
    if status_filter is not None:
        stmt = stmt.where(ProcessingJob.status == status_filter)
    if job_type_filter is not None:
        stmt = stmt.where(ProcessingJob.job_type == job_type_filter)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> ProcessingJob | None:
    return await session.get(ProcessingJob, job_id)


async def queue_counts(session: AsyncSession) -> dict[str, int]:
    """The Dashboard's "waiting/running/failed job counts" (spec §49) —
    a real aggregate query against `processing_jobs`, never fabricated."""
    counts: dict[str, int] = {}
    for label, statuses in (
        ("queued", [ProcessingStatus.QUEUED.value]),
        ("running", [ProcessingStatus.RUNNING.value]),
        ("failed", [ProcessingStatus.FAILED.value]),
    ):
        stmt = select(func.count()).select_from(ProcessingJob).where(
            ProcessingJob.status.in_(statuses)
        )
        result = await session.execute(stmt)
        counts[label] = int(result.scalar_one())
    return counts


# -- Workers ----------------------------------------------------------------


async def worker_role_status(
    session: AsyncSession, *, role: str, job_types: list[str]
) -> dict[str, object]:
    running_stmt = (
        select(func.count())
        .select_from(ProcessingJob)
        .where(
            ProcessingJob.job_type.in_(job_types),
            ProcessingJob.status == ProcessingStatus.RUNNING.value,
        )
    )
    running = int((await session.execute(running_stmt)).scalar_one())

    queued_stmt = (
        select(func.count())
        .select_from(ProcessingJob)
        .where(
            ProcessingJob.job_type.in_(job_types),
            ProcessingJob.status == ProcessingStatus.QUEUED.value,
        )
    )
    queued = int((await session.execute(queued_stmt)).scalar_one())

    active_worker_stmt = (
        select(ProcessingJob.worker_id)
        .where(
            ProcessingJob.job_type.in_(job_types),
            ProcessingJob.status == ProcessingStatus.RUNNING.value,
            ProcessingJob.worker_id.is_not(None),
        )
        .distinct()
    )
    active_worker_ids = sorted(
        {row[0] for row in (await session.execute(active_worker_stmt)).all() if row[0]}
    )

    last_activity_stmt = select(func.max(ProcessingJob.updated_at)).where(
        ProcessingJob.job_type.in_(job_types)
    )
    last_activity: datetime | None = (await session.execute(last_activity_stmt)).scalar_one()

    return {
        "role": role,
        "job_types": job_types,
        "running_jobs": running,
        "queued_jobs": queued,
        "active_worker_ids": active_worker_ids,
        "last_activity_at": last_activity,
    }


# -- Storage ------------------------------------------------------------


def directory_size_bytes(root: str | Path) -> int:
    """Real recursive size of everything under `root` — not fabricated,
    not sampled. Acceptable to walk the full tree for an admin-triggered,
    infrequent call (narrow scope, matching Phase 3's "avoid building a
    hardware inventory platform" precedent); a very large media volume
    would make this slow, logged as a known limitation rather than
    optimized away this phase."""
    total = 0
    path = Path(root)
    if not path.exists():
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                total += file_path.stat().st_size
            except OSError:  # noqa: PERF203 - race: file deleted mid-walk
                continue
    return total


def _disk_usage_of_nearest_existing_ancestor(root: str | Path) -> tuple[int, int]:
    """`shutil.disk_usage` requires the path to exist. The configured
    storage root may not have been created yet on a fresh install (it is
    created lazily by `LocalFilesystemStorage.__init__`/on first write) —
    walk up to the nearest existing ancestor directory so the Storage page
    still shows the real filesystem's total/free space rather than a
    fabricated 0."""
    import shutil

    path = Path(root).resolve()
    for candidate in [path, *path.parents]:
        if candidate.exists():
            usage = shutil.disk_usage(candidate)
            return usage.total, usage.free
    return 0, 0


def storage_usage(*, media_storage_root: str, model_volume_root: str) -> dict[str, object]:
    media_used = directory_size_bytes(media_storage_root)
    model_used = directory_size_bytes(model_volume_root)

    try:
        media_total, media_free = _disk_usage_of_nearest_existing_ancestor(media_storage_root)
    except OSError:
        media_total, media_free = 0, 0

    try:
        model_total, model_free = _disk_usage_of_nearest_existing_ancestor(model_volume_root)
    except OSError:
        model_total, model_free = 0, 0

    return {
        "media_storage_root": str(media_storage_root),
        "media_used_bytes": media_used,
        "media_disk_total_bytes": media_total,
        "media_disk_free_bytes": media_free,
        "model_volume_root": str(model_volume_root),
        "model_volume_used_bytes": model_used,
        "model_volume_disk_total_bytes": model_total,
        "model_volume_disk_free_bytes": model_free,
    }


# -- Hardware (CPU/RAM) ---------------------------------------------------


def detect_cpu_count() -> int | None:
    return os.cpu_count()


def detect_total_ram_mb() -> int | None:
    """Linux-only, stdlib-only best-effort (`/proc/meminfo`) — no `psutil`
    dependency added this phase (see Known Limitations). Returns None on
    any other platform or if the read fails; the Dashboard renders "not
    available" rather than a fabricated figure."""
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return None
    try:
        content = meminfo_path.read_text()
        match = re.search(r"MemTotal:\s+(\d+)\s+kB", content)
        if match:
            return int(match.group(1)) // 1024
    except OSError:
        return None
    return None


# -- About & Licenses -------------------------------------------------------


def _count_approval_statuses(text: str) -> dict[str, int]:
    """Counts `approval_status: <value>` occurrences in a compliance YAML
    file without adding a YAML-parsing runtime dependency (PyYAML is a
    dev-only tool per `compliance/check_licenses.py`'s own docstring) —
    the compliance YAML files' schema is a flat `approval_status: <word>`
    line per entry, so a plain regex count is exact, not an approximation."""
    counts: dict[str, int] = {"approved": 0, "review_required": 0, "blocked": 0, "unknown": 0}
    for match in re.finditer(r"^\s*approval_status:\s*(\w+)\s*$", text, re.MULTILINE):
        value = match.group(1)
        if value in counts:
            counts[value] += 1
    return counts


def resolve_repo_root() -> Path:
    """Best-effort: the compliance inventories / THIRD_PARTY_NOTICES.md
    live at the repository root, one level above `backend/`. In a local
    dev checkout that's `Path(__file__).parents[3]`; the production
    container image does NOT ship these files at all (they are not COPYed
    into `backend/Dockerfile` — the Docker build context is `backend/`
    only, one level below the repo root, so they're outside it) — callers
    must handle a resulting "file not found" gracefully rather than
    assume this path exists (see `docs/admin/about-and-licenses.md`)."""
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "THIRD_PARTY_NOTICES.md").exists():
        return candidate
    # Container fallback: WORKDIR is /app, one level above app/.
    return Path(__file__).resolve().parents[2]


def license_summary(compliance_dir: Path) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    files = {
        "direct_dependencies": "dependency-inventory.yml",
        "transitive_dependencies": "dependency-inventory-transitive.yml",
        "container_images": "container-inventory.yml",
        "ai_models": "model-inventory.yml",
    }
    for label, filename in files.items():
        file_path = compliance_dir / filename
        if file_path.exists():
            summary[label] = _count_approval_statuses(file_path.read_text())
    return summary


def third_party_notices_excerpt(repo_root: Path, *, max_chars: int = 4000) -> str:
    notices_path = repo_root / "THIRD_PARTY_NOTICES.md"
    if not notices_path.exists():
        return "THIRD_PARTY_NOTICES.md not found."
    content = notices_path.read_text()
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n... (truncated — see the full THIRD_PARTY_NOTICES.md file)"
