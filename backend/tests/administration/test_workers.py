"""Admin Portal Workers surface: derived from real `ProcessingJob` rows,
no new worker-registry table."""

from __future__ import annotations

from tests.administration.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio


async def test_workers_requires_system_admin(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/workers", headers=headers)
    assert resp.status_code == 403


async def test_workers_overview_reflects_real_queued_job(client, seeded, processing_env) -> None:  # noqa: ANN001
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
    workers_resp = await client.get("/api/v1/admin/workers", headers=carol_headers)
    assert workers_resp.status_code == 200, workers_resp.text
    roles = {w["role"]: w for w in workers_resp.json()["workers"]}
    assert set(roles.keys()) == {"worker-speech", "worker-diarization", "worker-extraction"}
    # NORMALIZE is queued to worker-speech's job types by the transcript
    # trigger — a real, non-fabricated queued count.
    assert roles["worker-speech"]["queued_jobs"] >= 1
