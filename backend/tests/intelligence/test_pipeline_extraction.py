"""End-to-end Phase 4 extraction tests: API request -> queued EXTRACT job
-> worker execution -> persisted ExtractedFact/FactEvidence/ReviewIssue ->
API read, plus the evidence-fabrication guard, uncertainty, contradiction
detection, and cross-organization authorization. No real Ollama/GPU/model
required — see tests/processing/conftest.py's FakeLLMProvider wiring.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.intelligence.models import ExtractedFact, FactStatus
from app.intelligence.service import run_extraction
from app.profiles.models import ModelProfilePurpose
from app.profiles.service import get_active_profile
from app.providers.llm import LLMProvider, LLMResponse
from app.review.models import ReviewIssue, ReviewIssueType, UncertaintyCategory
from app.transcription.models import Transcript, TranscriptSegment
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


class _StubLLMProvider(LLMProvider):
    """Returns crafted, schema-shaped JSON keyed off which category's
    schema was requested (identified by its distinctive top-level
    property) — deterministic, no real inference."""

    def __init__(self, responses_by_key: dict[str, dict[str, Any]]) -> None:
        self._responses = responses_by_key

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(text="", model_name="stub")

    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        props = json_schema.get("properties", {})
        for key in ("facts", "decisions", "tasks"):
            if key in props:
                payload = {key: self._responses.get(key, [])}
                return LLMResponse(text=json.dumps(payload), model_name="stub")
        raise AssertionError(f"unrecognized schema: {json_schema}")

    def status(self):  # pragma: no cover - not exercised by these tests
        raise NotImplementedError


async def _make_ready_conversation_with_transcript(client, headers, org_id, processing_env):
    _, sessionmaker, queue, storage = processing_env
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text
    await run_all_jobs(sessionmaker, queue, storage)
    return conversation_id


async def test_extract_requires_ready_transcript(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    # No transcript exists yet -> extraction must refuse, never run against nothing.
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract", json={}, headers=headers
    )
    assert resp.status_code == 409, resp.text


async def test_full_extraction_pipeline_with_fake_provider(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text

    _, sessionmaker, queue, storage = processing_env
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert resp.json()["status"] == "ready"  # transitions EXTRACTING -> READY on completion

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    assert resp.status_code == 200
    # FakeLLMProvider deliberately extracts nothing (never fabricates facts).
    assert resp.json() == []

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/review-issues", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_evidence_fabrication_is_never_trusted_and_missing_evidence_is_flagged(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env

    conversation_uuid = uuid.UUID(conversation_id)
    async with sessionmaker() as session:
        result = await session.execute(
            select(Transcript).where(Transcript.conversation_id == conversation_uuid)
        )
        transcript = result.scalars().first()
        assert transcript is not None
        segments = (
            (
                await session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == transcript.id)
                    .order_by(TranscriptSegment.sequence)
                )
            )
            .scalars()
            .all()
        )
        assert len(segments) >= 1
        real_sequence = segments[0].sequence

        provider = _StubLLMProvider(
            {
                "facts": [
                    {
                        "subject": "Ramipril",
                        "attribute": "dose",
                        "value": "5mg",
                        "certainty": "stated",
                        # Real, resolvable evidence.
                        "evidence_segment_sequences": [real_sequence],
                    },
                    {
                        "subject": "Ramipril",
                        "attribute": "dose",
                        "value": "10mg",
                        "certainty": "stated",
                        # A hallucinated/out-of-range segment number — must
                        # be discarded, never trusted as real evidence.
                        "evidence_segment_sequences": [999999],
                    },
                ],
                "decisions": [],
                "tasks": [],
            }
        )
        profile = await get_active_profile(session, purpose=ModelProfilePurpose.EXTRACTION)
        assert profile is not None

        outcome = await run_extraction(
            session,
            conversation_id=conversation_uuid,
            transcript=transcript,
            processing_run_id=None,
            provider=provider,
            profile=profile,
        )
        await session.commit()

        assert outcome.facts_created == 2

        result = await session.execute(
            select(ExtractedFact).where(ExtractedFact.conversation_id == conversation_uuid)
        )
        facts = {f.structured_value["value"]: f for f in result.scalars().all()}

        verified_fact = facts["5mg"]
        assert verified_fact.status == FactStatus.VERIFIED.value

        unverified_fact = facts["10mg"]
        assert unverified_fact.status == FactStatus.UNVERIFIED.value

        # The hallucinated sequence must never produce a FactEvidence row.
        from app.evidence.models import FactEvidence

        evidence_result = await session.execute(
            select(FactEvidence).where(FactEvidence.fact_id == unverified_fact.id)
        )
        assert evidence_result.scalars().all() == []

        # A MISSING_EVIDENCE review issue must exist for the unverified fact.
        issues_result = await session.execute(
            select(ReviewIssue).where(
                ReviewIssue.conversation_id == conversation_uuid,
                ReviewIssue.uncertainty_category == UncertaintyCategory.MISSING_EVIDENCE.value,
            )
        )
        missing_evidence_issues = issues_result.scalars().all()
        assert any(str(unverified_fact.id) in i.related_fact_ids for i in missing_evidence_issues)

        # A conflicting dose for the same subject/attribute is a real,
        # detected contradiction.
        contradiction_result = await session.execute(
            select(ReviewIssue).where(
                ReviewIssue.conversation_id == conversation_uuid,
                ReviewIssue.issue_type == ReviewIssueType.POTENTIAL_CONTRADICTION.value,
            )
        )
        contradictions = contradiction_result.scalars().all()
        assert len(contradictions) == 1
        assert {str(verified_fact.id), str(unverified_fact.id)} == set(
            contradictions[0].related_fact_ids
        )


async def test_cross_organization_facts_and_evidence_return_404(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract",
        json={},
        headers=alice_headers,
    )
    assert resp.status_code == 202
    _, sessionmaker, queue, storage = processing_env
    await run_all_jobs(sessionmaker, queue, storage)

    bob_headers = await login(client, "bob", "another very strong pw 456")

    # Bob (Org B) must never learn this conversation/its facts/review-issues
    # exist, regardless of guessing the correct UUID.
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=bob_headers)
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/review-issues", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract", json={}, headers=bob_headers
    )
    assert resp.status_code == 404

    fact_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}", headers=bob_headers
    )
    assert resp.status_code == 404
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/evidence", headers=bob_headers
    )
    assert resp.status_code == 404


async def test_missing_permission_is_rejected(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Auditor role has fact:read but not fact:extract."""
    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

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
            OrganizationMembership(user_id=dana.id, organization_id=uuid_from(seeded["org_a"]))
        )
        await session.commit()

    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )

    dana_headers = await login(client, "dana", "a reasonably strong pw 000")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/extract", json={}, headers=dana_headers
    )
    assert resp.status_code == 403

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=dana_headers)
    assert resp.status_code == 200  # Auditor does have fact:read


def uuid_from(value: str):
    import uuid

    return uuid.UUID(value)
