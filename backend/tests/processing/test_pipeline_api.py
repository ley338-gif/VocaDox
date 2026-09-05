"""End-to-end Phase 3 pipeline tests: API request -> queued jobs -> worker
execution (against Fake providers) -> persisted Transcript/DetectedSpeaker
-> API read/correct/assign, plus authorization, idempotency, retry, and
worker-crash-recovery coverage. No real Postgres/Valkey/GPU/model
required — see tests/processing/conftest.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.processing.models import ProcessingJob, ProcessingStatus
from app.processing.service import reclaim_stale_jobs
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


async def _process_and_wait(client, headers, conversation_id, **body):  # noqa: ANN001
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json=body, headers=headers
    )
    return resp


async def test_end_to_end_transcript_and_diarization(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    resp = await _process_and_wait(client, headers, conversation_id)
    assert resp.status_code == 202, resp.text
    transcript_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/transcript", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == transcript_id
    assert resp.json()["status"] == "ready"
    assert resp.json()["provider"] == "fake"

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    assert resp.status_code == 200
    segments = resp.json()
    assert len(segments) > 0
    assert all(s["original_text"] for s in segments)
    # FakeDiarizationProvider always reports 2 speakers.
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    assert resp.status_code == 200
    speakers = resp.json()
    assert len(speakers) == 2

    resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert resp.json()["status"] == "ready"


async def test_transcript_provider_reflects_the_worker_that_actually_ran_it(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Regression test for a real bug found manually testing a local
    deployment with a real speech provider configured on worker-speech
    but not on the backend/api container (the architecturally-intended
    split — see docker-compose.yml's `backend` service comment: the api
    "never loads a real speech/diarization provider itself... kept at
    the safe 'fake' default here regardless").

    `create_transcript` initially writes provider/model from the API
    process's own (here: default fake) provider before the job is even
    dispatched. If nothing corrects those fields once the job actually
    runs, the Transcript's provenance metadata is just wrong whenever
    the process that answers `POST .../process/transcript` differs from
    the process that actually transcribes — exactly the case with the
    real two-container topology. This test simulates that divergence
    with two *different* fake providers standing in for "api's own
    (irrelevant) provider" vs. "what worker-speech is really running",
    and asserts the persisted Transcript ends up with the worker's real
    values, not the api's initial placeholder.
    """
    from app.processing.queues import DIARIZATION_WORKER_JOB_TYPES, SPEECH_WORKER_JOB_TYPES
    from app.providers.speech_to_text import FakeSpeechProvider, SpeechProviderStatus
    from app.workers.processing_worker import ProcessingWorker

    class _RealWorkerSpeechProvider(FakeSpeechProvider):
        """Stands in for a real provider configured only on the speech
        worker — distinguishable provider/model identity from whatever
        the api/backend process's own `get_speech_provider()` reports."""

        def status(self) -> SpeechProviderStatus:
            return SpeechProviderStatus(
                provider="faster-whisper",
                model="Systran/faster-whisper-small",
                model_revision="536b0662742c02347bc0e980a01041f333bce12",
                installed=True,
                device="cpu",
                cuda_available=False,
                detail="stand-in for a real worker-side provider in this test",
            )

    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    resp = await _process_and_wait(client, headers, conversation_id, diarize=False)
    assert resp.status_code == 202, resp.text
    # The api process's own (default fake) provider wrote this initial,
    # soon-to-be-stale placeholder value.
    assert resp.json()["provider"] == "fake"

    speech_worker = ProcessingWorker(
        worker_id="test-speech-real",
        job_types=SPEECH_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
        speech_provider=_RealWorkerSpeechProvider(),
    )
    # diarize=False still needs an ALIGN pass to finalize the transcript
    # as "ready" (with honestly UNASSIGNED segments — see
    # test_process_without_diarize_still_produces_transcript below); the
    # provider it uses is irrelevant to what this test is checking, so a
    # plain default worker is enough.
    diarization_worker = ProcessingWorker(
        worker_id="test-diarization-default",
        job_types=DIARIZATION_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
    )
    # Job creation writes a Transactional Outbox row rather than enqueuing
    # directly (Phase 3.1) — each worker's own maintenance sweep relays
    # it, which only happens as a side effect of `run_forever` below. So
    # run at least once unconditionally before checking whether more work
    # is left, mirroring `run_all_jobs`'s loop in this same conftest.
    for _ in range(6):
        await speech_worker.run_forever(max_iterations=1)
        await diarization_worker.run_forever(max_iterations=1)
        pending = sum(len(v) for v in queue._queues.values())  # noqa: SLF001
        if pending == 0:
            break

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/transcript", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    # Corrected to what the worker that actually ran it used — not the
    # api process's stale initial placeholder.
    assert body["provider"] == "faster-whisper"
    assert body["model"] == "Systran/faster-whisper-small"
    assert body["model_revision"] == "536b0662742c02347bc0e980a01041f333bce12"


async def test_process_without_diarize_still_produces_transcript(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    resp = await _process_and_wait(client, headers, conversation_id, diarize=False)
    assert resp.status_code == 202
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/transcript", headers=headers)
    assert resp.json()["status"] == "ready"

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    segments = resp.json()
    assert len(segments) > 0
    # No diarization requested -> alignment produces UNASSIGNED, honest,
    # never a guessed speaker.
    assert all(s["alignment_quality"] == "unassigned" for s in segments)
    assert all(s["speaker_id"] is None for s in segments)
    assert all(s["review_flag"] for s in segments)


async def test_process_is_idempotent_without_reprocess(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    resp1 = await _process_and_wait(client, headers, conversation_id)
    resp2 = await _process_and_wait(client, headers, conversation_id)
    assert resp1.json()["id"] == resp2.json()["id"]


async def test_reprocess_creates_new_transcript_and_deactivates_old(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    resp1 = await _process_and_wait(client, headers, conversation_id)
    await run_all_jobs(sessionmaker, queue, storage)
    first_id = resp1.json()["id"]

    resp2 = await _process_and_wait(client, headers, conversation_id, reprocess=True)
    assert resp2.status_code == 202
    second_id = resp2.json()["id"]
    assert second_id != first_id
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/transcript", headers=headers)
    assert resp.json()["id"] == second_id


async def test_cross_organization_transcript_access_is_404_not_403(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, alice_headers, organization_id=seeded["org_a"]
    )
    await _process_and_wait(client, alice_headers, conversation_id)
    await run_all_jobs(sessionmaker, queue, storage)

    bob_headers = await login(client, "bob", "another very strong pw 456")
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/processing", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/speakers", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript",
        json={},
        headers=bob_headers,
    )
    assert resp.status_code == 404


async def test_segment_correction_never_overwrites_original_text(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_wait(client, headers, conversation_id)
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    segment = resp.json()[0]
    original_text = segment["original_text"]

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/transcript/segments/{segment['id']}",
        json={"corrected_text": "This is a corrected version."},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["original_text"] == original_text  # untouched
    assert body["corrected_text"] == "This is a corrected version."
    assert body["review_status"] == "corrected"


async def test_speaker_assignment_and_unassignment(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_wait(client, headers, conversation_id)
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    speaker = resp.json()[0]
    assert speaker["display_label"] is None

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/speakers/{speaker['id']}",
        json={"display_label": "Dr. Muster"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["display_label"] == "Dr. Muster"
    assert resp.json()["assigned_by_user_id"] is not None

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/speakers/{speaker['id']}",
        json={},
        headers=headers,
    )
    assert resp.json()["display_label"] is None


async def test_retry_requeues_a_failed_job_as_a_new_job(client, seeded, processing_env) -> None:  # noqa: ANN001
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_wait(client, headers, conversation_id)

    async with sessionmaker() as session:
        result = await session.execute(
            select(ProcessingJob).where(ProcessingJob.conversation_id.is_not(None))
        )
        job = result.scalars().first()
        job.status = ProcessingStatus.FAILED.value
        job.failure_class = "permanent"
        job.error_code = "INPUT_INVALID"
        job.error_message_safe = "simulated failure"
        await session.commit()

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/processing/retry", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/processing", headers=headers
    )
    job_types_and_statuses = [(j["job_type"], j["status"]) for j in resp.json()["jobs"]]
    assert ("normalize", "queued") in job_types_and_statuses


async def test_worker_lease_expiry_reclaims_stale_running_job(seeded, processing_env) -> None:  # noqa: ANN001
    """Simulates the 'job RUNNING, worker disappears' scenario (spec:
    'Worker crash recovery') by building a real conversation+job, forcing
    its lease into the past, then asserting reclaim_stale_jobs requeues it
    rather than leaving it stuck RUNNING forever."""
    _, sessionmaker, queue, storage = processing_env
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=processing_env[0]), base_url="https://testserver"
    ) as ac:
        headers = await login(ac, "alice", "a very strong password 123")
        conversation_id, _ = await create_conversation_with_source_audio(
            ac, headers, organization_id=seeded["org_a"]
        )
        resp = await ac.post(
            f"/api/v1/conversations/{conversation_id}/process/transcript",
            json={},
            headers=headers,
        )
        assert resp.status_code == 202

    async with sessionmaker() as session:
        result = await session.execute(select(ProcessingJob))
        job = result.scalars().first()
        job.status = ProcessingStatus.RUNNING.value
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        job.worker_id = "dead-worker"
        await session.commit()

        reclaimed = await reclaim_stale_jobs(session, queue)
        await session.commit()
        assert len(reclaimed) == 1
        assert reclaimed[0].status == ProcessingStatus.QUEUED.value
        assert reclaimed[0].error_code == "WORKER_LEASE_EXPIRED"
