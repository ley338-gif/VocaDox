"""Protokoll generation: real transcript (via the fake speech provider) ->
a crafted stub LLM response -> persisted ProtocolRevision/Section/Item/
Source. The single most important test here mirrors Phase 4's evidence-
fabrication guard: a section/item citing a transcript segment sequence
that does not actually exist on this transcript must never produce a
ProtocolSource row for it -- silently dropped, never fabricated.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.platform.version import APPLICATION_VERSION
from app.processing.models import ProcessingRun, RunStatus, RunType
from app.profiles.models import ModelProfilePurpose
from app.profiles.service import get_active_profile
from app.protocols.models import (
    Protocol,
    ProtocolItem,
    ProtocolRevision,
    ProtocolSection,
    ProtocolSource,
)
from app.protocols.service import run_protocol_generation
from app.providers.llm import LLMProvider, LLMResponse
from app.transcription.models import Transcript
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import make_ready_conversation_with_transcript


class _StubLLMProvider(LLMProvider):
    """Returns one fixed, crafted `ProtocolGenerationResult`-shaped JSON
    payload regardless of the prompt — deterministic, no real inference.
    `payload` is injected per-test so each test can control exactly which
    segment sequences are cited (including a nonexistent one, for the
    fabrication-guard test)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

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
        return LLMResponse(text=json.dumps(self._payload), model_name="stub")

    def status(self):  # pragma: no cover - not exercised by these tests
        raise NotImplementedError


async def _run_generation(session, conversation_id: uuid.UUID, payload: dict[str, Any]):
    result = await session.execute(
        select(Transcript).where(Transcript.conversation_id == conversation_id)
    )
    transcript = result.scalars().first()
    assert transcript is not None

    profile = await get_active_profile(session, purpose=ModelProfilePurpose.EXTRACTION)
    assert profile is not None

    run = ProcessingRun(
        conversation_id=conversation_id,
        source_media_id=transcript.source_media_id,
        run_type=RunType.PROTOCOL_GENERATION.value,
        status=RunStatus.RUNNING.value,
        provider="stub",
        model="stub",
        application_version=APPLICATION_VERSION,
    )
    session.add(run)
    await session.flush()

    outcome = await run_protocol_generation(
        session,
        conversation_id=conversation_id,
        transcript=transcript,
        processing_run_id=run.id,
        provider=_StubLLMProvider(payload),
        profile=profile,
    )
    await session.commit()
    return outcome


async def test_generation_persists_sections_items_and_resolves_real_sources(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env

    # The fake speech provider always produces exactly segments 0 and 1
    # (see app.providers.speech_to_text.FakeSpeechProvider) -- both real,
    # cited here alongside a nonexistent sequence 99 to prove the
    # fabrication guard.
    payload = {
        "sections": [
            {
                "section_type": "introduction",
                "title": "Begrüßung",
                "summary": "Kurze Einleitung.",
                "items": [],
                "source_segment_sequences": [0],
            },
            {
                "section_type": "action_items",
                "title": "Nächste Schritte",
                "summary": "Vereinbarte Aufgaben.",
                "items": [
                    {
                        "item_type": "action_item",
                        "text": "Bericht fertigstellen",
                        "responsible_label": "Dr. Müller",
                        "due_date": "nächste Woche",
                        "source_segment_sequences": [1, 99],
                    }
                ],
                "source_segment_sequences": [1, 99],
            },
        ]
    }

    import uuid as _uuid

    async with sessionmaker() as session:
        outcome = await _run_generation(session, _uuid.UUID(conversation_id), payload)
        assert outcome.section_count == 2
        assert outcome.item_count == 1

    async with sessionmaker() as session:
        result = await session.execute(
            select(Protocol).where(Protocol.conversation_id == _uuid.UUID(conversation_id))
        )
        protocol = result.scalar_one()
        assert protocol.current_revision_id is not None

        revision = await session.get(ProtocolRevision, protocol.current_revision_id)
        assert revision is not None
        assert revision.revision_number == 1

        sections_result = await session.execute(
            select(ProtocolSection)
            .where(ProtocolSection.protocol_revision_id == revision.id)
            .order_by(ProtocolSection.position)
        )
        sections = list(sections_result.scalars().all())
        assert len(sections) == 2
        assert sections[0].section_type == "introduction"
        assert sections[1].section_type == "action_items"

        # The real cited segment (0) resolves to a source; the section's
        # start/end ms come from that real segment, never fabricated.
        intro_sources = await session.execute(
            select(ProtocolSource).where(ProtocolSource.protocol_section_id == sections[0].id)
        )
        assert len(list(intro_sources.scalars().all())) == 1
        assert sections[0].start_ms is not None

        # The action_items section cited [1, 99] -- only segment 1 is
        # real, so exactly one ProtocolSource, never two, never one for
        # the nonexistent sequence 99.
        action_sources = await session.execute(
            select(ProtocolSource).where(ProtocolSource.protocol_section_id == sections[1].id)
        )
        assert len(list(action_sources.scalars().all())) == 1

        items_result = await session.execute(
            select(ProtocolItem).where(ProtocolItem.protocol_section_id == sections[1].id)
        )
        items = list(items_result.scalars().all())
        assert len(items) == 1
        assert items[0].responsible_label == "Dr. Müller"
        assert items[0].due_date == "nächste Woche"

        # Same fabrication guard at the item level: [1, 99] -> exactly one
        # real ProtocolSource, sequence 99 silently dropped.
        item_sources = await session.execute(
            select(ProtocolSource).where(ProtocolSource.protocol_item_id == items[0].id)
        )
        assert len(list(item_sources.scalars().all())) == 1


async def test_regeneration_creates_new_revision_never_mutates_prior(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env

    payload = {
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

    import uuid as _uuid

    async with sessionmaker() as session:
        first = await _run_generation(session, _uuid.UUID(conversation_id), payload)
    async with sessionmaker() as session:
        second = await _run_generation(session, _uuid.UUID(conversation_id), payload)

    assert first.revision_id != second.revision_id

    async with sessionmaker() as session:
        result = await session.execute(
            select(Protocol).where(Protocol.conversation_id == _uuid.UUID(conversation_id))
        )
        protocol = result.scalar_one()
        assert protocol.current_revision_id == second.revision_id

        revisions_result = await session.execute(
            select(ProtocolRevision)
            .where(ProtocolRevision.protocol_id == protocol.id)
            .order_by(ProtocolRevision.revision_number)
        )
        revisions = list(revisions_result.scalars().all())
        assert [r.revision_number for r in revisions] == [1, 2]

        # The first revision's own section is untouched, not deleted or
        # rewritten by the second generation.
        first_sections = await session.execute(
            select(ProtocolSection).where(ProtocolSection.protocol_revision_id == revisions[0].id)
        )
        assert len(list(first_sections.scalars().all())) == 1
