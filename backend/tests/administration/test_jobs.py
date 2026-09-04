"""Admin Portal "Jobs" surface: `GET /admin/jobs` lists real
`ProcessingJob` rows (not a mockup) and `POST /admin/jobs/{id}/retry`
reuses the existing retry mechanism, permission-gated to `system:admin`
(global, cross-organization visibility — an elevated capability beyond the
per-conversation `processing:read`/`processing:retry` a standard user
already has for their own conversations)."""

from __future__ import annotations

import uuid

from app.processing.models import ProcessingJob, ProcessingStatus
from sqlalchemy import select

from tests.administration.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio


async def test_list_jobs_requires_system_admin(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/jobs", headers=alice_headers)
    assert resp.status_code == 403


async def test_list_jobs_shows_real_queued_job(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, alice_headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript",
        json={},
        headers=alice_headers,
    )
    assert resp.status_code == 202, resp.text

    carol_headers = await login(client, "carol", "yet another strong pw 789")
    list_resp = await client.get("/api/v1/admin/jobs", headers=carol_headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] >= 1
    conversation_ids = {item["conversation_id"] for item in body["items"]}
    assert conversation_id in conversation_ids

    filtered = await client.get(
        "/api/v1/admin/jobs", params={"status": "queued"}, headers=carol_headers
    )
    assert filtered.status_code == 200
    assert all(item["status"] == "queued" for item in filtered.json()["items"])


async def test_retry_failed_job_requeues_it(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, alice_headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript",
        json={},
        headers=alice_headers,
    )
    assert resp.status_code == 202, resp.text

    # Force the freshly-queued job into a terminal FAILED state directly
    # (simulating what `fail_job` would do after exhausting retries) so the
    # admin retry action has something real to act on.
    async with sessionmaker() as session:
        job = (
            await session.execute(
                select(ProcessingJob).where(
                    ProcessingJob.conversation_id == uuid.UUID(conversation_id),
                )
            )
        ).scalars().first()
        assert job is not None
        job_id = str(job.id)
        job.status = ProcessingStatus.FAILED.value
        job.error_code = "TEST_FORCED_FAILURE"
        job.error_message_safe = "forced failure for test"
        await session.commit()

    carol_headers = await login(client, "carol", "yet another strong pw 789")
    retry_resp = await client.post(f"/api/v1/admin/jobs/{job_id}/retry", headers=carol_headers)
    assert retry_resp.status_code == 200, retry_resp.text
    assert retry_resp.json()["status"] == "queued"
    assert retry_resp.json()["attempt"] == 0

    # Retrying an already-queued job is rejected (only FAILED is eligible).
    second_attempt = await client.post(f"/api/v1/admin/jobs/{job_id}/retry", headers=carol_headers)
    assert second_attempt.status_code == 409


async def test_retry_requires_system_admin(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/jobs/00000000-0000-0000-0000-000000000000/retry",
        headers=alice_headers,
    )
    assert resp.status_code == 403
