"""Protokoll generation pipeline: Transcript -> one structured LLM call ->
ProtocolRevision (Sections + Items + Sources) -- see
docs/architecture/adr/0042-protokoll.md.

`run_protocol_generation` is called by the async worker
(app.processing.orchestrator.execute_generate_protocol), never inline in
an HTTP request handler -- same discipline as
app.intelligence.service.run_extraction.

A `ProtocolRevision` (and its sections/items/sources) is only ever
created here, on a successfully validated LLM response -- there is no
"pending" row created before the call, matching how `run_extraction`
only ever creates `ExtractedFact` rows after a validated response, never
before. A caller polling "is generation in progress" reads the
`ProcessingJob`'s own status, not a Protocol row (see
app.protocols.router).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.profiles.models import ModelProfile
from app.protocols.models import (
    Protocol,
    ProtocolItem,
    ProtocolRevision,
    ProtocolRevisionStatus,
    ProtocolSection,
    ProtocolSource,
)
from app.protocols.prompts import SYSTEM_PROMPT, build_prompt
from app.protocols.schemas import ProtocolGenerationResult
from app.providers.llm import LLMProvider
from app.transcription.models import Transcript, TranscriptSegment
from app.transcription.rendering import build_transcript_text, load_speaker_labels

# Same rationale/cap as app.intelligence.service._MAX_TRANSCRIPT_CHARS --
# a protocol needs the conversation's overall shape, so it gets a larger
# budget than one extraction category call, but still a real, honest,
# documented limit rather than a silent full-transcript send.
_MAX_TRANSCRIPT_CHARS = 20000


class ProtocolGenerationValidationError(RuntimeError):
    """The LLM's structured response did not validate against
    `ProtocolGenerationResult`. Classified as a PERMANENT job failure --
    retrying with identical input would produce the identical error."""


@dataclass(frozen=True, slots=True)
class ProtocolGenerationOutcome:
    revision_id: uuid.UUID
    section_count: int
    item_count: int


async def _load_segments(
    session: AsyncSession, transcript_id: uuid.UUID
) -> list[TranscriptSegment]:
    result = await session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.sequence)
    )
    return list(result.scalars().all())


async def _get_or_create_protocol(session: AsyncSession, *, conversation_id: uuid.UUID) -> Protocol:
    result = await session.execute(
        select(Protocol).where(Protocol.conversation_id == conversation_id)
    )
    protocol = result.scalar_one_or_none()
    if protocol is None:
        protocol = Protocol(conversation_id=conversation_id)
        session.add(protocol)
        await session.flush()
    return protocol


def _resolve_sources(
    segments_by_sequence: dict[int, TranscriptSegment], claimed_sequences: list[int]
) -> list[TranscriptSegment]:
    """Only claimed sequence numbers that resolve to a REAL segment of
    THIS transcript are returned -- a hallucinated/out-of-range sequence
    number is silently discarded, never trusted, never surfaced as if it
    were real evidence (same discipline as
    app.intelligence.service._resolve_evidence)."""
    resolved: list[TranscriptSegment] = []
    seen: set[uuid.UUID] = set()
    for seq in claimed_sequences:
        segment = segments_by_sequence.get(seq)
        if segment is not None and segment.id not in seen:
            resolved.append(segment)
            seen.add(segment.id)
    return resolved


async def run_protocol_generation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    transcript: Transcript,
    processing_run_id: uuid.UUID,
    provider: LLMProvider,
    profile: ModelProfile,
) -> ProtocolGenerationOutcome:
    segments = await _load_segments(session, transcript.id)
    if not segments:
        raise ValueError("transcript has no segments to generate a protocol from")
    segments_by_sequence = {s.sequence: s for s in segments}

    speaker_ids = {s.speaker_id for s in segments if s.speaker_id is not None}
    speaker_labels = await load_speaker_labels(session, speaker_ids)
    transcript_text = build_transcript_text(
        segments, speaker_labels, max_chars=_MAX_TRANSCRIPT_CHARS
    )

    prompt = build_prompt(transcript_text)
    response = await provider.complete_structured(
        prompt,
        json_schema=ProtocolGenerationResult.model_json_schema(),
        system_prompt=SYSTEM_PROMPT,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
    )
    try:
        raw = json.loads(response.text)
        validated = ProtocolGenerationResult.model_validate(raw)
    except (json.JSONDecodeError, pydantic.ValidationError) as exc:
        raise ProtocolGenerationValidationError(
            f"LLM response failed schema validation: {exc}"
        ) from exc

    protocol = await _get_or_create_protocol(session, conversation_id=conversation_id)
    result = await session.execute(
        select(ProtocolRevision.revision_number)
        .where(ProtocolRevision.protocol_id == protocol.id)
        .order_by(ProtocolRevision.revision_number.desc())
    )
    last_number = result.scalars().first() or 0

    revision = ProtocolRevision(
        protocol_id=protocol.id,
        revision_number=last_number + 1,
        status=ProtocolRevisionStatus.READY.value,
        processing_run_id=processing_run_id,
    )
    session.add(revision)
    await session.flush()

    item_count = 0
    for section_position, gen_section in enumerate(validated.sections):
        section_sources = _resolve_sources(
            segments_by_sequence, gen_section.source_segment_sequences
        )
        start_ms = min((s.start_ms for s in section_sources), default=None)
        end_ms = max((s.end_ms for s in section_sources), default=None)
        section = ProtocolSection(
            protocol_revision_id=revision.id,
            position=section_position,
            section_type=gen_section.section_type,
            title=gen_section.title,
            summary=gen_section.summary,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        session.add(section)
        await session.flush()
        for source_segment in section_sources:
            session.add(
                ProtocolSource(
                    protocol_section_id=section.id,
                    transcript_segment_id=source_segment.id,
                )
            )

        for item_position, gen_item in enumerate(gen_section.items):
            item_sources = _resolve_sources(
                segments_by_sequence, gen_item.source_segment_sequences
            )
            item = ProtocolItem(
                protocol_section_id=section.id,
                position=item_position,
                item_type=gen_item.item_type,
                text=gen_item.text,
                responsible_label=gen_item.responsible_label,
                due_date=gen_item.due_date,
            )
            session.add(item)
            await session.flush()
            item_count += 1
            for source_segment in item_sources:
                session.add(
                    ProtocolSource(
                        protocol_item_id=item.id,
                        transcript_segment_id=source_segment.id,
                    )
                )

    protocol.current_revision_id = revision.id
    await session.flush()

    return ProtocolGenerationOutcome(
        revision_id=revision.id,
        section_count=len(validated.sections),
        item_count=item_count,
    )
