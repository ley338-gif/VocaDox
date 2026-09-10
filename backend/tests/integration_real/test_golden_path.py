"""Focused application golden path against real PostgreSQL and Valkey.

The ordinary suite deliberately stays fast on SQLite/in-process fakes. This
module runs only when ``VOCADOX_REAL_INFRA_TESTS=1`` and proves that the actual
database dialect, Valkey-backed sessions/outbox queues, API routes and workers
compose into one evidence-preserving workflow.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from app.core.storage import get_storage_provider
from app.identity.seed import apply_seed as apply_identity_seed
from app.identity.service import (
    add_user_to_group,
    assign_role_to_group,
    create_local_user,
    get_or_create_group,
    get_role_by_name,
)
from app.media.normalizer import NoOpMediaNormalizer
from app.organizations.models import Organization, OrganizationMembership
from app.platform.db.session import get_engine, get_sessionmaker
from app.platform.valkey.valkey_backend import get_valkey_backend
from app.processing.models import ProcessingJob, ProcessingStatus
from app.processing.outbox import relay_pending_outbox
from app.processing.queues import QUEUE_NAMES, queue_name_for
from app.profiles.seed import apply_processing_profile_seed
from app.profiles.seed import apply_seed as apply_model_profile_seed
from app.providers.diarization import FakeDiarizationProvider
from app.providers.llm import LLMProvider, LLMProviderStatus, LLMResponse
from app.providers.speech_to_text import FakeSpeechProvider
from app.templates.seed import apply_seed as apply_template_seed
from app.workers.processing_worker import ProcessingWorker
from sqlalchemy import select, text
from tests.conversations.conftest import make_wav_bytes

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("VOCADOX_REAL_INFRA_TESTS") != "1",
        reason="requires the separate PostgreSQL/Valkey integration environment",
    ),
]


class GoldenPathLLMProvider(LLMProvider):
    """Deterministic evidence-bearing output; never calls a model or network."""

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(text="", model_name="golden-path-stub")

    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        properties = json_schema.get("properties", {})
        if "facts" in properties:
            payload = {
                "facts": [
                    {
                        "subject": "Test conversation",
                        "attribute": "statement",
                        "value": "This is a fake transcript segment.",
                        "certainty": "stated",
                        "evidence_segment_sequences": [0],
                    }
                ]
            }
        elif "decisions" in properties:
            payload = {"decisions": []}
        elif "tasks" in properties:
            payload = {"tasks": []}
        elif "sections" in properties:
            payload = {
                "sections": [
                    {
                        "section_type": "facts",
                        "title": "Verified statement",
                        "summary": "One statement is grounded in the transcript.",
                        "items": [
                            {
                                "item_type": "fact",
                                "text": "This is a fake transcript segment.",
                                "source_segment_sequences": [0],
                            }
                        ],
                        "source_segment_sequences": [0],
                    }
                ]
            }
        else:  # pragma: no cover - protects the test from unnoticed schema expansion
            raise AssertionError(f"unexpected structured schema: {properties.keys()}")
        return LLMResponse(text=json.dumps(payload), model_name="golden-path-stub")

    def status(self) -> LLMProviderStatus:
        return LLMProviderStatus(
            provider="fake",
            model="golden-path-stub",
            model_revision=None,
            installed=True,
            device="cpu",
            structured_output=True,
        )


async def _seed_operator() -> tuple[str, str, str]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await apply_identity_seed(session)
        await apply_model_profile_seed(session)
        await apply_template_seed(session)
        await apply_processing_profile_seed(session)

        organization = Organization(name="Golden Path Organization", slug="golden-path")
        session.add(organization)
        await session.flush()

        role = await get_role_by_name(session, "System Admin")
        assert role is not None
        password = "golden path strong password 2026"
        user = await create_local_user(
            session,
            username="golden-admin",
            password=password,
            display_name="Golden Admin",
        )
        group = await get_or_create_group(session, name="Golden Path Administrators")
        await assign_role_to_group(session, group_id=group.id, role_id=role.id)
        await add_user_to_group(session, user_id=user.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=user.id, organization_id=organization.id)
        )
        await session.commit()
        return str(organization.id), user.username, password


async def _drain_real_queues(*, max_rounds: int = 30) -> None:
    sessionmaker = get_sessionmaker()
    queue = get_valkey_backend()
    storage = get_storage_provider()
    llm = GoldenPathLLMProvider()
    workers = {
        job_type: ProcessingWorker(
            worker_id=f"golden-{job_type.value}",
            job_types=[job_type],
            sessionmaker=sessionmaker,
            queue=queue,
            storage=storage,
            normalizer=NoOpMediaNormalizer(),
            speech_provider=FakeSpeechProvider(),
            diarization_provider=FakeDiarizationProvider(),
            llm_provider=llm,
        )
        for job_type in QUEUE_NAMES
    }

    for _ in range(max_rounds):
        async with sessionmaker() as session:
            await relay_pending_outbox(session, queue)
            await session.commit()
        pending_types = [
            job_type
            for job_type in QUEUE_NAMES
            if await queue.queue_length(queue_name_for(job_type)) > 0
        ]
        if not pending_types:
            break
        for job_type in pending_types:
            await workers[job_type].run_forever(max_iterations=1)
    else:
        pytest.fail("real-infrastructure processing queues did not drain")

    async with sessionmaker() as session:
        jobs = list((await session.execute(select(ProcessingJob))).scalars().all())
        assert jobs
        assert all(job.status == ProcessingStatus.SUCCEEDED.value for job in jobs)


async def test_evidence_chain_golden_path_uses_real_postgres_and_valkey(client) -> None:  # noqa: ANN001
    engine = get_engine()
    assert engine.dialect.name == "postgresql"
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1

    queue = get_valkey_backend()
    assert await queue.ping()
    organization_id, username, password = await _seed_operator()

    login = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}
    session_token = client.cookies.get("vocadox_session")
    assert session_token
    assert await queue.get(f"identity:session:{session_token}") is not None

    created = await client.post(
        "/api/v1/conversations",
        json={"title": "Real infrastructure golden path", "organization_id": organization_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/v1/conversations/{conversation_id}/media",
        files={"file": ("synthetic.wav", make_wav_bytes(duration_s=1.0), "audio/wav")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text

    started = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript",
        json={},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    await _drain_real_queues()

    transcript = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript", headers=headers
    )
    assert transcript.status_code == 200, transcript.text
    assert transcript.json()["status"] == "ready"
    segments_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    segments = segments_response.json()
    assert segments_response.status_code == 200
    assert segments[0]["original_text"] == "This is a fake transcript segment."

    extracted = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract", json={}, headers=headers
    )
    assert extracted.status_code == 202, extracted.text
    await _drain_real_queues()

    facts_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/facts", headers=headers
    )
    facts = facts_response.json()
    assert facts_response.status_code == 200
    assert len(facts) == 1
    fact_id = facts[0]["id"]
    assert facts[0]["status"] == "verified"

    evidence_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/evidence", headers=headers
    )
    evidence = evidence_response.json()
    assert evidence_response.status_code == 200
    assert len(evidence) == 1
    assert evidence[0]["transcript_segment_id"] == segments[0]["id"]
    assert evidence[0]["segment_text"] == segments[0]["original_text"]

    protocol_started = await client.post(
        f"/api/v1/conversations/{conversation_id}/protocol/generate", json={}, headers=headers
    )
    assert protocol_started.status_code == 202, protocol_started.text
    await _drain_real_queues()
    protocol_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/protocol", headers=headers
    )
    protocol = protocol_response.json()
    assert protocol_response.status_code == 200
    item = protocol["current_revision"]["sections"][0]["items"][0]
    protocol_sources_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/protocol/items/{item['id']}/sources",
        headers=headers,
    )
    protocol_sources = protocol_sources_response.json()
    assert protocol_sources_response.status_code == 200
    assert protocol_sources[0]["transcript_segment_id"] == segments[0]["id"]

    composed = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert composed.status_code == 200, composed.text
    revision = composed.json()["current_revision"]
    document_fact_ids = {
        linked_fact_id
        for section in revision["structured_content"]
        for statement in section["statements"]
        for linked_fact_id in statement["fact_ids"]
    }
    assert fact_id in document_fact_ids

    approved = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/approve", headers=headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    exported = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=text", headers=headers
    )
    assert exported.status_code == 200, exported.text
    assert "This is a fake transcript segment." in exported.text
