"""Worker/GPU/Queue Metrics and Model Storage (Phase 11, roadmap §73).

Extends Phase 7's `app.administration` Dashboard/Jobs/Workers read-model
and reuses Phase 3's `app.providers.device` hardware detection — no
parallel worker-registry or hardware-inventory table (same restraint
Phase 3/7 already established: "avoid building a hardware inventory
platform"). Every number here is a real aggregate over `ProcessingJob`/
`ProcessingRun` rows or a real filesystem/subprocess read; anything not
reliably available renders as `None` ("not available"), never a
fabricated value.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.administration.service import directory_size_bytes
from app.processing.models import ProcessingJob, ProcessingStatus
from app.providers.device import DeviceCapabilities, detect_device_capabilities

# -- Worker metrics -----------------------------------------------------


async def worker_throughput(
    session: AsyncSession, *, job_types: list[str], now: datetime | None = None
) -> dict[str, object]:
    """Real aggregates over `ProcessingJob.updated_at` — how many jobs of
    this role's job_types succeeded/failed in the last 1h/24h, and mean
    duration (`completed_at - started_at`, only over rows that recorded
    both) for jobs that succeeded in the last 24h. No time-series store
    exists, so this is a rolling-window aggregate rather than a stored
    trend line — see Known Limitations in PHASE_11_VALIDATION_REPORT.md."""
    now = now or datetime.now(UTC)
    window_1h = now - timedelta(hours=1)
    window_24h = now - timedelta(hours=24)

    async def _count(status_value: str, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ProcessingJob)
            .where(
                ProcessingJob.job_type.in_(job_types),
                ProcessingJob.status == status_value,
                ProcessingJob.updated_at >= since,
            )
        )
        return int((await session.execute(stmt)).scalar_one())

    succeeded_1h = await _count(ProcessingStatus.SUCCEEDED.value, window_1h)
    succeeded_24h = await _count(ProcessingStatus.SUCCEEDED.value, window_24h)
    failed_24h = await _count(ProcessingStatus.FAILED.value, window_24h)

    duration_stmt = select(ProcessingJob.started_at, ProcessingJob.completed_at).where(
        ProcessingJob.job_type.in_(job_types),
        ProcessingJob.status == ProcessingStatus.SUCCEEDED.value,
        ProcessingJob.updated_at >= window_24h,
        ProcessingJob.started_at.is_not(None),
        ProcessingJob.completed_at.is_not(None),
    )
    rows = (await session.execute(duration_stmt)).all()
    durations = [
        (completed - started).total_seconds()
        for started, completed in rows
        if started is not None and completed is not None
    ]
    avg_duration_seconds = round(sum(durations) / len(durations), 2) if durations else None

    return {
        "succeeded_last_1h": succeeded_1h,
        "succeeded_last_24h": succeeded_24h,
        "failed_last_24h": failed_24h,
        "avg_duration_seconds_last_24h": avg_duration_seconds,
        "sample_count_last_24h": len(durations),
    }


# -- GPU metrics ----------------------------------------------------------


def gpu_metrics() -> dict[str, object]:
    """Reuses Phase 3's `detect_device_capabilities` unchanged for
    presence/name/VRAM. Utilization percent is additionally attempted via
    `nvidia-smi` (present on any host with the NVIDIA driver installed,
    independent of whether torch/ctranslate2 are importable in THIS
    process) — best-effort, exception-safe, returns None (never a
    fabricated number) if `nvidia-smi` isn't on PATH or the query fails."""
    caps: DeviceCapabilities = detect_device_capabilities()
    utilization_percent = _nvidia_smi_utilization() if caps.cuda_available else None
    return {
        "cuda_available": caps.cuda_available,
        "device_name": caps.device_name,
        "total_vram_mb": caps.total_vram_mb,
        "free_vram_mb": caps.free_vram_mb,
        "utilization_percent": utilization_percent,
    }


def _nvidia_smi_utilization() -> int | None:
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed args, no user input
            [
                binary,
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return None
        first_line = result.stdout.strip().splitlines()[0].strip()
        return int(first_line)
    except Exception:  # noqa: BLE001 - metrics must never raise
        return None


# -- Queue metrics ----------------------------------------------------------


async def queue_depth_by_job_type(session: AsyncSession) -> list[dict[str, object]]:
    """Real current depth (queued + running) per job_type — a finer-
    grained view than Phase 7 Dashboard's single aggregate queue_counts."""
    stmt = (
        select(ProcessingJob.job_type, ProcessingJob.status, func.count())
        .where(
            ProcessingJob.status.in_(
                [ProcessingStatus.QUEUED.value, ProcessingStatus.RUNNING.value]
            )
        )
        .group_by(ProcessingJob.job_type, ProcessingJob.status)
    )
    rows = (await session.execute(stmt)).all()
    by_type: dict[str, dict[str, int]] = {}
    for job_type, status_value, count in rows:
        by_type.setdefault(job_type, {"queued": 0, "running": 0})
        by_type[job_type][status_value] = int(count)
    return [
        {"job_type": job_type, "queued": counts["queued"], "running": counts["running"]}
        for job_type, counts in sorted(by_type.items())
    ]


async def queue_throughput_hourly(
    session: AsyncSession, *, hours: int = 24, now: datetime | None = None
) -> list[dict[str, object]]:
    """Real hourly buckets of succeeded/failed job completions over the
    last `hours` — computed in Python (not SQL date_trunc, which SQLite
    doesn't support and this codebase's test suite runs against SQLite)
    from `ProcessingJob.updated_at` on already-terminal rows. This is the
    "queue depth/throughput trend" the phase brief asks for; it is a
    real, bounded rolling window, not a durably stored time-series
    (there is no metrics-history table — see Known Limitations)."""
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    stmt = select(ProcessingJob.status, ProcessingJob.updated_at).where(
        ProcessingJob.status.in_([ProcessingStatus.SUCCEEDED.value, ProcessingStatus.FAILED.value]),
        ProcessingJob.updated_at >= since,
    )
    rows = (await session.execute(stmt)).all()

    buckets: dict[datetime, dict[str, int]] = {}
    for i in range(hours):
        bucket_start = (now - timedelta(hours=hours - 1 - i)).replace(
            minute=0, second=0, microsecond=0
        )
        buckets[bucket_start] = {"succeeded": 0, "failed": 0}

    for status_value, updated_at in rows:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        bucket_start = updated_at.replace(minute=0, second=0, microsecond=0)
        if bucket_start in buckets:
            key = "succeeded" if status_value == ProcessingStatus.SUCCEEDED.value else "failed"
            buckets[bucket_start][key] += 1

    return [
        {"hour_start": hour, "succeeded": counts["succeeded"], "failed": counts["failed"]}
        for hour, counts in sorted(buckets.items())
    ]


# -- Model storage ----------------------------------------------------------


def model_storage_overview(model_volume_root: str) -> dict[str, object]:
    """Admin visibility into the models volume specifically (spec: "Model
    Storage... as a distinct view from Phase 7's general conversation-
    media Storage page"). Lists each top-level directory under the model
    volume root — matching how `app.cli.install_models`/`model_manager`
    lay out installed model profiles (one directory per profile name,
    e.g. `speech-default/`, `diarization-default/`) — with a real
    recursive size for each. Never mixes this with
    `media_storage_root` (ADR-0018's "don't mix model files with
    Conversation media" principle)."""
    root = Path(model_volume_root)
    entries: list[dict[str, object]] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir():
                entries.append(
                    {"name": child.name, "size_bytes": directory_size_bytes(child)}
                )
    total_bytes = directory_size_bytes(root)
    return {
        "model_volume_root": str(model_volume_root),
        "total_bytes": total_bytes,
        "models": entries,
    }
