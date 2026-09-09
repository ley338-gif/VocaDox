"""Protokoll REST surface: async trigger mechanics (202 -> job -> worker ->
persisted revision, real Postgres/SQLite job dispatch, not just the
service function directly — see test_generation.py for that), 404 before
generation, and permission gating."""

from __future__ import annotations

import uuid

from app.identity.service import (
    add_user_to_group,
    assign_role_to_group,
    create_local_user,
    get_or_create_group,
    get_role_by_name,
)
from app.organizations.models import OrganizationMembership
from app.profiles.models import ModelProfilePurpose
from app.profiles.service import get_active_profile
from app.protocols.service import run_protocol_generation
from app.transcription.models import Transcript
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import make_ready_conversation_with_transcript
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


async def test_generate_requires_ready_transcript(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/protocol/generate", json={}, headers=headers
    )
    assert resp.status_code == 409, resp.text


async def test_get_protocol_before_generation_is_404(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/protocol", headers=headers)
    assert resp.status_code == 404


async def test_full_generation_pipeline_with_fake_provider(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Proves the real async plumbing (permission gate -> job creation ->
    worker dispatch -> ProcessingRun -> ProtocolRevision) works end to
    end, complementing test_generation.py's direct-service-call tests
    (which cover the fabrication-guard content logic with a crafted
    stub). FakeLLMProvider deliberately generates zero sections (never
    fabricates content), same discipline as the equivalent extraction
    test."""
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/protocol/generate", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text

    _, sessionmaker, queue, storage = processing_env
    await run_all_jobs(sessionmaker, queue, storage)

    # Generation never touches Conversation.status (unlike extraction).
    resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert resp.json()["status"] == "ready"

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/protocol", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_revision"]["revision_number"] == 1
    assert body["current_revision"]["status"] == "ready"
    assert body["current_revision"]["sections"] == []

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/protocol/revisions", headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_generate_missing_permission_is_rejected(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Auditor role has protocol:read but not protocol:generate."""
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        auditor_role = await get_role_by_name(session, "Auditor")
        assert auditor_role is not None
        dana = await create_local_user(
            session, username="dana", password="a reasonably strong pw 000", display_name="Dana"
        )
        group = await get_or_create_group(session, name="Org A Auditors")
        await assign_role_to_group(session, group_id=group.id, role_id=auditor_role.id)
        await add_user_to_group(session, user_id=dana.id, group_id=group.id)
        session.add(
            OrganizationMembership(
                user_id=dana.id, organization_id=uuid.UUID(seeded["org_a"])
            )
        )
        await session.commit()

    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )

    dana_headers = await login(client, "dana", "a reasonably strong pw 000")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/protocol/generate", json={}, headers=dana_headers
    )
    assert resp.status_code == 403

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/protocol", headers=dana_headers
    )
    assert resp.status_code == 404  # Auditor does have protocol:read; just no protocol yet


async def test_sources_endpoints_return_real_segment_data(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env

    async with sessionmaker() as session:
        result = await session.execute(
            select(Transcript).where(Transcript.conversation_id == uuid.UUID(conversation_id))
        )
        transcript = result.scalars().first()
        assert transcript is not None
        profile = await get_active_profile(session, purpose=ModelProfilePurpose.EXTRACTION)
        assert profile is not None

        from app.platform.version import APPLICATION_VERSION
        from app.processing.models import ProcessingRun, RunStatus, RunType

        from tests.protocols.test_generation import _StubLLMProvider

        run = ProcessingRun(
            conversation_id=uuid.UUID(conversation_id),
            source_media_id=transcript.source_media_id,
            run_type=RunType.PROTOCOL_GENERATION.value,
            status=RunStatus.RUNNING.value,
            provider="stub",
            model="stub",
            application_version=APPLICATION_VERSION,
        )
        session.add(run)
        await session.flush()
        await run_protocol_generation(
            session,
            conversation_id=uuid.UUID(conversation_id),
            transcript=transcript,
            processing_run_id=run.id,
            provider=_StubLLMProvider(
                {
                    "sections": [
                        {
                            "section_type": "note",
                            "title": "Notiz",
                            "summary": "Eine Notiz.",
                            "items": [],
                            "source_segment_sequences": [0],
                        }
                    ]
                }
            ),
            profile=profile,
        )
        await session.commit()

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/protocol", headers=headers)
    section_id = resp.json()["current_revision"]["sections"][0]["id"]

    sources_resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/protocol/sections/{section_id}/sources",
        headers=headers,
    )
    assert sources_resp.status_code == 200, sources_resp.text
    sources = sources_resp.json()
    assert len(sources) == 1
    assert sources[0]["segment_text"] == "This is a fake transcript segment."
    assert sources[0]["segment_start_ms"] == 0
