"""GET /admin/analytics/technical: real ProcessingJob-derived metrics
(Phase 8) — reuses the exact Phase 3 job-tracking table, no duplicate
tracking. Verifies against directly-inserted rows with known counts/
timestamps so the computed success-rate/latency figures are checkable
exactly, not just "some number came back"."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.processing.models import JobType, ProcessingJob, ProcessingStatus
from httpx import AsyncClient

from tests.analytics.conftest import login


async def test_technical_analytics_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/analytics/technical", headers=headers)
    assert resp.status_code == 403


async def test_technical_analytics_real_success_rate_and_latency(
    client: AsyncClient, app_env, seeded  # noqa: ANN001
) -> None:
    app, sessionmaker = app_env
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        # 2 succeeded TRANSCRIBE jobs (10s and 20s latency), 1 failed.
        for started_offset, latency in ((0, 10), (5, 20)):
            job = ProcessingJob(
                conversation_id=uuid.uuid4(),
                source_media_id=uuid.uuid4(),
                job_type=JobType.TRANSCRIBE.value,
                status=ProcessingStatus.SUCCEEDED.value,
                queued_at=now,
                started_at=now + timedelta(seconds=started_offset),
                completed_at=now + timedelta(seconds=started_offset + latency),
            )
            session.add(job)
        session.add(
            ProcessingJob(
                conversation_id=uuid.uuid4(),
                source_media_id=uuid.uuid4(),
                job_type=JobType.TRANSCRIBE.value,
                status=ProcessingStatus.FAILED.value,
                queued_at=now,
            )
        )
        await session.commit()

    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/analytics/technical", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_jobs"] == 3
    transcribe = body["by_job_type"]["transcribe"]
    assert transcribe["succeeded"] == 2
    assert transcribe["failed"] == 1
    assert transcribe["success_rate"] == pytest.approx(2 / 3)
    assert transcribe["avg_latency_seconds"] == pytest.approx(15.0)
    # Response is structurally counts/labels only.
    assert set(body.keys()) == {"window_days", "total_jobs", "volume_by_day", "by_job_type"}
