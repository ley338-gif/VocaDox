"""Shared fixtures for the Phase 3 processing/transcription/diarization
integration tests: builds on tests.conversations.conftest's app/seeded
fixtures (same in-memory SQLite + fake cache pattern) and adds a
FakeQueueBackend (an in-process stand-in for Valkey's QueueBackend,
identical in spirit to FakeCacheBackend) so the full pipeline — API
request -> queued ProcessingJob -> worker execution against FakeSpeech/
FakeDiarization providers -> persisted Transcript -> API read — can run
end-to-end with no real Postgres/Valkey/GPU/model required.
"""

from __future__ import annotations

from collections import defaultdict

import pytest_asyncio
from app.core.ai_providers import get_queue_backend
from app.core.storage import get_storage_provider
from app.platform.valkey.backends import QueueBackend
from app.processing.queues import (
    DIARIZATION_WORKER_JOB_TYPES,
    EXTRACTION_WORKER_JOB_TYPES,
    SPEECH_WORKER_JOB_TYPES,
)
from app.providers.llm import FakeLLMProvider
from app.providers.storage import LocalFilesystemStorage
from app.workers.processing_worker import ProcessingWorker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conversations.conftest import (  # noqa: F401
    app_env,
    client,
    login,
    make_wav_bytes,
    seeded,
)


class FakeQueueBackend(QueueBackend):
    """FIFO in-process queue keyed by queue name. `dequeue`'s
    `timeout_seconds` is ignored (returns immediately) — tests drive the
    worker explicitly rather than waiting on a real blocking pop."""

    def __init__(self) -> None:
        self._queues: dict[str, list[str]] = defaultdict(list)

    async def enqueue(self, queue_name: str, payload: str) -> None:
        self._queues[queue_name].append(payload)

    async def dequeue(self, queue_name: str, *, timeout_seconds: int = 5) -> str | None:
        q = self._queues[queue_name]
        if not q:
            return None
        return q.pop(0)

    async def queue_length(self, queue_name: str) -> int:
        return len(self._queues[queue_name])


@pytest_asyncio.fixture
async def processing_env(app_env, tmp_path):  # noqa: ANN001, F811
    app, sessionmaker = app_env
    queue = FakeQueueBackend()
    storage = LocalFilesystemStorage(tmp_path / "media")

    app.dependency_overrides[get_queue_backend] = lambda: queue
    app.dependency_overrides[get_storage_provider] = lambda: storage

    yield app, sessionmaker, queue, storage


async def run_all_jobs(
    sessionmaker: async_sessionmaker, queue: FakeQueueBackend, storage, *, max_rounds: int = 20
) -> None:
    """Drains the fake queues to completion by alternating a speech-role
    and a diarization-role worker (mirroring the real two-service
    topology) until both queues are empty. Deterministic and fast — no
    sleeping, since FakeQueueBackend never blocks."""
    speech_worker = ProcessingWorker(
        worker_id="test-speech",
        job_types=SPEECH_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
    )
    diarization_worker = ProcessingWorker(
        worker_id="test-diarization",
        job_types=DIARIZATION_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
    )
    extraction_worker = ProcessingWorker(
        worker_id="test-extraction",
        job_types=EXTRACTION_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
        llm_provider=FakeLLMProvider(),
    )
    from app.processing.models import OutboxStatus, ProcessingOutbox
    from sqlalchemy import select

    for _ in range(max_rounds):
        # Job creation (API request or a worker's own success-handler
        # chaining) writes a Transactional Outbox row rather than enqueuing
        # onto FakeQueueBackend directly (Phase 3.1 — see
        # app.processing.outbox). Each worker's own maintenance sweep would
        # normally relay this, but that only happens as a side effect of
        # `run_forever` below, which itself only runs if `pending` (queue
        # depth) is nonzero — so check outstanding outbox rows too, or a
        # freshly-created job that hasn't been relayed yet looks like "no
        # work left" and the loop exits before the worker ever sees it.
        async with sessionmaker() as session:
            outstanding_outbox = (
                await session.execute(
                    select(ProcessingOutbox.id).where(
                        ProcessingOutbox.status == OutboxStatus.PENDING.value
                    )
                )
            ).scalars().first()
        pending = sum(len(v) for v in queue._queues.values())  # noqa: SLF001
        if pending == 0 and outstanding_outbox is None:
            break
        await speech_worker.run_forever(max_iterations=1)
        await diarization_worker.run_forever(max_iterations=1)
        await extraction_worker.run_forever(max_iterations=1)


async def create_conversation_with_source_audio(
    http_client: AsyncClient,
    headers: dict[str, str],
    *,
    organization_id: str,
    processing_profile_id: str | None = None,
) -> tuple[str, str]:
    """Returns (conversation_id, source_media_id). `processing_profile_id`
    (Phase 6) is optional — omitted means the SYSTEM DEFAULT config
    hierarchy layer applies (see app.profiles.resolver), unchanged from
    every pre-Phase-6 caller of this helper."""
    body: dict[str, str] = {"title": "Processing test", "organization_id": organization_id}
    if processing_profile_id:
        body["processing_profile_id"] = processing_profile_id
    resp = await http_client.post(
        "/api/v1/conversations",
        json=body,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conversation_id = resp.json()["id"]

    wav_bytes = make_wav_bytes(duration_s=1.0)
    files = {"file": ("source.wav", wav_bytes, "audio/wav")}
    resp = await http_client.post(
        f"/api/v1/conversations/{conversation_id}/media", files=files, headers=headers
    )
    assert resp.status_code == 201, resp.text
    media_id = resp.json()["id"]
    return conversation_id, media_id
