"""Shared fact-seeding helper for Phase 5 document/review-wizard tests.
Reuses the exact `_StubLLMProvider` pattern from
tests/intelligence/test_pipeline_extraction.py to inject deterministic,
real facts (persisted via the real `run_extraction` pipeline, not a
hand-built fixture row) including one genuine contradiction + one genuine
missing-evidence case, so approval-blocking has something real to block
on.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.intelligence.service import run_extraction
from app.profiles.models import ModelProfilePurpose
from app.profiles.service import get_active_profile
from app.providers.llm import LLMProvider, LLMResponse
from app.transcription.models import Transcript, TranscriptSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


class StubLLMProvider(LLMProvider):
    def __init__(self, responses_by_key: dict[str, list[dict[str, Any]]]) -> None:
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
                payload = json.dumps({key: self._responses.get(key, [])})
                return LLMResponse(text=payload, model_name="stub")
        raise AssertionError(f"unrecognized schema: {json_schema}")

    def status(self):  # pragma: no cover - not exercised
        raise NotImplementedError


async def make_ready_conversation_with_transcript(client, headers, org_id, processing_env) -> str:  # noqa: ANN001
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


async def seed_facts_with_contradiction_and_clean_fact(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> dict[str, Any]:
    """Persists three facts via the real extraction pipeline against a
    stub provider:
    - a VERIFIED, clean general_fact (long evidence text, no issues) —
      composable with no blocking review issue.
    - a VERIFIED "5mg" dose fact + an UNVERIFIED "10mg" dose fact for the
      same subject/attribute (hallucinated evidence) — produces a real
      MISSING_EVIDENCE (critical) + USER_REVIEW_REQUIRED (high) +
      POTENTIAL_CONTRADICTION (high) review issue, exactly like
      tests/intelligence/test_pipeline_extraction.py's fabrication-guard
      test, so approval has something real to block on.

    Returns fact ids by structured `value` for tests to look up.
    """
    result = await session.execute(
        select(Transcript).where(Transcript.conversation_id == conversation_id)
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

    provider = StubLLMProvider(
        {
            "facts": [
                {
                    "subject": "Ramipril",
                    "attribute": "dose",
                    "value": "5mg",
                    "certainty": "stated",
                    "evidence_segment_sequences": [real_sequence],
                },
                {
                    "subject": "Ramipril",
                    "attribute": "dose",
                    "value": "10mg",
                    "certainty": "stated",
                    "evidence_segment_sequences": [999999],  # hallucinated — never trusted
                },
                {
                    "subject": "Follow-up clinic",
                    "attribute": "location",
                    "value": "Building B, room 4",
                    "certainty": "stated",
                    "evidence_segment_sequences": [real_sequence],
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
        conversation_id=conversation_id,
        transcript=transcript,
        processing_run_id=None,
        provider=provider,
        profile=profile,
    )
    await session.commit()
    assert outcome.facts_created == 3

    from app.intelligence.models import ExtractedFact

    facts_result = await session.execute(
        select(ExtractedFact).where(ExtractedFact.conversation_id == conversation_id)
    )
    by_value = {f.structured_value["value"]: f for f in facts_result.scalars().all()}
    return {
        "verified_fact_id": by_value["5mg"].id,
        "unverified_fact_id": by_value["10mg"].id,
        "clean_fact_id": by_value["Building B, room 4"].id,
    }
