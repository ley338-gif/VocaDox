"""Extraction pipeline: Transcript -> Structured Facts -> Evidence Mapping
-> Schema Validation -> Consistency Checks -> Contradictions -> Review
Issues (spec §23/§24) — never `Transcript -> "write a report" -> Document`.

`run_extraction` is called by the async worker (app.processing.orchestrator
.execute_extract), never inline in an HTTP request handler.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.models import Conversation
from app.evidence.models import EvidenceType, FactEvidence
from app.intelligence.contradictions import FactForContradictionCheck, detect_contradictions
from app.intelligence.models import (
    Certainty,
    ExtractedFact,
    FactCategory,
    FactRedactionEvent,
    FactStatus,
)
from app.intelligence.prompts import SYSTEM_PROMPT, build_prompt_from_instruction
from app.intelligence.rendering import render_fact_statement
from app.intelligence.schemas import NOT_MENTIONED
from app.intelligence.uncertainty import classify as classify_uncertainty
from app.profiles.models import ModelProfile
from app.providers.llm import LLMProvider
from app.review.models import ReviewIssue, ReviewIssueStatus, ReviewIssueType
from app.search.models import SearchSourceType
from app.search.service import delete_search_entry, upsert_search_entry
from app.templates.models import TemplateVersion
from app.templates.schema_builder import ResolvedCategory, resolve_categories
from app.transcription.models import Transcript, TranscriptSegment
from app.transcription.rendering import (
    build_transcript_text,
    load_speaker_labels,
    segment_text,
)

# Hard cap on how much transcript text one extraction call sends, in
# characters. Long conversations are truncated (oldest-first kept, most
# recent segments dropped) rather than silently sent whole and risking a
# provider-side context overflow with no visible error — a real, honest
# limitation documented in docs/architecture/intelligence-pipeline.md, not
# a hidden failure mode.
_MAX_TRANSCRIPT_CHARS = 12000


class ExtractionValidationError(RuntimeError):
    """The LLM's structured response did not validate against the
    category's Pydantic schema. Classified as a PERMANENT job failure —
    retrying with identical input would produce the identical error."""


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    facts_created: int
    review_issues_created: int
    facts_by_category: dict[str, int]


async def _load_segments(
    session: AsyncSession, transcript_id: uuid.UUID
) -> list[TranscriptSegment]:
    result = await session.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.sequence)
    )
    return list(result.scalars().all())


# _segment_text/_load_speaker_labels/_segment_line/_build_transcript_text
# moved to app.transcription.rendering (Post-GA Protokoll needed the same
# speaker-labeled transcript text a second caller) — see that module for
# the implementations; thin wrappers below keep this module's call sites
# (and _MAX_TRANSCRIPT_CHARS's meaning) unchanged.
_segment_text = segment_text


async def _load_speaker_labels(
    session: AsyncSession, speaker_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    return await load_speaker_labels(session, speaker_ids)


def _build_transcript_text(
    segments: list[TranscriptSegment], speaker_labels: dict[uuid.UUID, str]
) -> str:
    return build_transcript_text(segments, speaker_labels, max_chars=_MAX_TRANSCRIPT_CHARS)


async def _extract_category(
    provider: LLMProvider,
    profile: ModelProfile,
    resolved: ResolvedCategory,
    transcript_text: str,
    system_prompt: str,
) -> list[dict]:
    json_schema = resolved.schema_cls.model_json_schema()
    prompt = build_prompt_from_instruction(resolved.instruction, transcript_text)
    response = await provider.complete_structured(
        prompt,
        json_schema=json_schema,
        system_prompt=system_prompt,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
    )
    try:
        raw = json.loads(response.text)
        validated = resolved.schema_cls.model_validate(raw)
    except (json.JSONDecodeError, pydantic.ValidationError) as exc:
        raise ExtractionValidationError(
            f"category={resolved.key}: LLM response failed schema validation: {exc}"
        ) from exc
    items = getattr(validated, resolved.item_field)
    return [item.model_dump() for item in items]


async def _resolve_evidence(
    session: AsyncSession,
    *,
    transcript_id: uuid.UUID,
    segments_by_sequence: dict[int, TranscriptSegment],
    fact_id: uuid.UUID,
    claimed_sequences: list[int],
) -> tuple[bool, float | None, int | None]:
    """Only claimed sequence numbers that resolve to a REAL segment of
    THIS transcript become FactEvidence rows — a hallucinated/out-of-range
    sequence number is silently discarded (never trusted, never surfaced
    as if it were real evidence). Returns
    (has_any_resolved_evidence, avg_segment_confidence, evidence_char_count).
    """
    resolved: list[TranscriptSegment] = []
    for seq in claimed_sequences:
        segment = segments_by_sequence.get(seq)
        if segment is not None:
            resolved.append(segment)

    for segment in resolved:
        session.add(
            FactEvidence(
                fact_id=fact_id,
                transcript_segment_id=segment.id,
                evidence_type=EvidenceType.EVIDENCE_SPOKEN.value,
            )
        )

    if not resolved:
        return False, None, None

    confidences = [s.confidence for s in resolved if s.confidence is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else None
    char_count = sum(len(_segment_text(s)) for s in resolved)
    return True, avg_confidence, char_count


async def _supersede_previous_facts(session: AsyncSession, *, conversation_id: uuid.UUID) -> None:
    """A fresh extraction run always represents the conversation's current,
    complete state, so every fact from an earlier run is marked
    `FactStatus.SUPERSEDED` — never deleted (the audit trail, and any
    `FactCorrection`s on it, stay intact), just hidden from every "current
    state" read (Fakten tab, Document composition, the Aufgaben sync — see
    each one's own `status != superseded` filter). A conversation being
    extracted for the first time has nothing to supersede: a harmless
    no-op, so first-extraction behavior is unchanged.

    Also resolves the direct consequence for Review Issues: an OPEN issue
    whose `related_fact_ids` are now entirely superseded is moved to
    ACKNOWLEDGED (an existing, otherwise-unused ReviewIssueStatus) rather
    than left open forever, which would otherwise permanently block
    Document approval (`app.documents.service._open_blocking_issues`) over
    a fact nobody can even see anymore. This deliberately never touches
    `resolved_status`/`resolved_fact_id`/`resolved_by_user_id` — those stay
    reserved for a real human Review Wizard action."""
    result = await session.execute(
        select(ExtractedFact).where(
            ExtractedFact.conversation_id == conversation_id,
            ExtractedFact.status != FactStatus.SUPERSEDED.value,
        )
    )
    previous_facts = list(result.scalars().all())
    if not previous_facts:
        return
    superseded_ids = {str(f.id) for f in previous_facts}
    for fact in previous_facts:
        fact.status = FactStatus.SUPERSEDED.value
        await delete_search_entry(
            session, source_type=SearchSourceType.EXTRACTED_FACT, source_id=fact.id
        )

    open_issues_result = await session.execute(
        select(ReviewIssue).where(
            ReviewIssue.conversation_id == conversation_id,
            ReviewIssue.status == ReviewIssueStatus.OPEN.value,
        )
    )
    for issue in open_issues_result.scalars().all():
        if issue.related_fact_ids and set(issue.related_fact_ids) <= superseded_ids:
            issue.status = ReviewIssueStatus.ACKNOWLEDGED.value
    await session.flush()


async def run_extraction(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    transcript: Transcript,
    processing_run_id: uuid.UUID | None,
    provider: LLMProvider,
    profile: ModelProfile,
    template_version: TemplateVersion | None = None,
    system_prompt: str | None = None,
    category_instruction_overrides: dict[str, str] | None = None,
) -> ExtractionOutcome:
    """`template_version` (Phase 6) drives which categories are extracted —
    defaults to the "general" template's published version (the exact same
    3 builtin categories Phase 4/5 hardcoded) when omitted, so every
    existing caller (including every pre-Phase-6 test) keeps its exact
    prior behavior unchanged. `system_prompt`/`category_instruction_overrides`
    similarly default to the template's own wording unless an admin has
    published a different `PromptVersion` for it (see
    app.processing.orchestrator.execute_extract, which is the only caller
    that ever passes them) — this is how a published PromptVersion actually
    changes extraction behavior, not just gets recorded for provenance."""
    if template_version is None:
        from app.templates.service import get_default_template_version

        template_version = await get_default_template_version(session)
    resolved_categories = resolve_categories(template_version.extraction_categories)
    if category_instruction_overrides:
        resolved_categories = [
            r if r.key not in category_instruction_overrides
            else ResolvedCategory(
                key=r.key,
                fact_type=r.fact_type,
                item_field=r.item_field,
                schema_cls=r.schema_cls,
                instruction=category_instruction_overrides[r.key],
            )
            for r in resolved_categories
        ]
    effective_system_prompt = system_prompt or SYSTEM_PROMPT

    await _supersede_previous_facts(session, conversation_id=conversation_id)

    from app.conversations.models import Conversation

    conversation = await session.get(Conversation, conversation_id)
    assert conversation is not None

    segments = await _load_segments(session, transcript.id)
    segments_by_sequence = {s.sequence: s for s in segments}
    speaker_ids = {s.speaker_id for s in segments if s.speaker_id is not None}
    speaker_labels = await _load_speaker_labels(session, speaker_ids)
    transcript_text = _build_transcript_text(segments, speaker_labels)

    facts_by_category: dict[str, int] = {}
    created_facts: list[ExtractedFact] = []
    uncertainty_issues_created = 0

    for resolved in resolved_categories:
        category = resolved.key
        fact_type = resolved.fact_type
        items = await _extract_category(
            provider, profile, resolved, transcript_text, effective_system_prompt
        )
        facts_by_category[category] = 0
        for item in items:
            certainty = Certainty(item["certainty"])
            fact = ExtractedFact(
                conversation_id=conversation_id,
                processing_run_id=processing_run_id,
                category=category,
                fact_type=fact_type,
                structured_value=item,
                certainty=certainty.value,
                confidence=None,
                status=FactStatus.UNVERIFIED.value,
            )
            session.add(fact)
            await session.flush()

            has_evidence, avg_confidence, char_count = await _resolve_evidence(
                session,
                transcript_id=transcript.id,
                segments_by_sequence=segments_by_sequence,
                fact_id=fact.id,
                claimed_sequences=item.get("evidence_segment_sequences", []),
            )
            fact.status = FactStatus.VERIFIED.value if has_evidence else FactStatus.UNVERIFIED.value
            await upsert_search_entry(
                session,
                conversation_id=conversation.id,
                organization_id=conversation.organization_id,
                group_id=conversation.group_id,
                source_type=SearchSourceType.EXTRACTED_FACT,
                source_id=fact.id,
                content=render_fact_statement(fact),
            )

            field_values = [
                v for k, v in item.items() if k not in ("certainty", "evidence_segment_sequences")
                and isinstance(v, str)
            ]
            signals = classify_uncertainty(
                certainty=certainty,
                has_evidence=has_evidence,
                avg_segment_confidence=avg_confidence,
                field_values=field_values,
                evidence_text_char_count=char_count,
            )
            for signal in signals:
                session.add(
                    ReviewIssue(
                        conversation_id=conversation_id,
                        issue_type=ReviewIssueType.UNCERTAINTY.value,
                        severity=signal.severity.value,
                        uncertainty_category=signal.category.value,
                        related_fact_ids=[str(fact.id)],
                        description=signal.description,
                    )
                )
                uncertainty_issues_created += 1

            created_facts.append(fact)
            facts_by_category[category] += 1

    await session.flush()

    # Contradiction check across ALL non-superseded GENERAL_FACT facts for
    # this conversation (not just this run's) so a contradiction against an
    # earlier extraction run is still caught.
    existing_result = await session.execute(
        select(ExtractedFact).where(
            ExtractedFact.conversation_id == conversation_id,
            ExtractedFact.category == FactCategory.GENERAL_FACT.value,
            ExtractedFact.status != FactStatus.SUPERSEDED.value,
        )
    )
    all_general_facts = list(existing_result.scalars().all())
    check_inputs = [
        FactForContradictionCheck(
            fact_id=f.id,
            category=f.category,
            subject=f.structured_value.get("subject", ""),
            attribute=f.structured_value.get("attribute", ""),
            value=f.structured_value.get("value", ""),
        )
        for f in all_general_facts
        if f.structured_value.get("value") != NOT_MENTIONED
    ]
    contradictions = detect_contradictions(check_inputs)
    contradiction_issues_created = 0
    for c in contradictions:
        session.add(
            ReviewIssue(
                conversation_id=conversation_id,
                issue_type=ReviewIssueType.POTENTIAL_CONTRADICTION.value,
                severity="high",
                uncertainty_category=None,
                related_fact_ids=[str(c.fact_id_a), str(c.fact_id_b)],
                description=(
                    f"Conflicting values for '{c.subject}' / '{c.attribute}': "
                    f"'{c.value_a}' vs '{c.value_b}'."
                ),
            )
        )
        contradiction_issues_created += 1

    await session.flush()

    total_review_issues = uncertainty_issues_created + contradiction_issues_created
    if total_review_issues > 0:
        # Phase 10 (spec §55): the one genuine "review.required" trigger
        # point in the codebase — a real ReviewIssue row was just created,
        # not a synthetic mapping. IDs/counts only, never fact content.
        await record_event(
            session,
            event_type="review.required",
            event_metadata={
                "conversation_id": str(conversation_id),
                "review_issues_created": total_review_issues,
            },
        )

    return ExtractionOutcome(
        facts_created=len(created_facts),
        review_issues_created=total_review_issues,
        facts_by_category=facts_by_category,
    )


async def _resync_search_entry(session: AsyncSession, fact: ExtractedFact) -> None:
    """Re-renders this fact's search index entry after its redaction
    state changes — render_fact_statement already returns the redacted
    placeholder when appropriate, so this is the same upsert every other
    fact-mutation call site already performs, just triggered by a
    redaction event instead of creation/correction."""
    conversation = await session.get(Conversation, fact.conversation_id)
    if conversation is None:
        return
    await upsert_search_entry(
        session,
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        group_id=conversation.group_id,
        source_type=SearchSourceType.EXTRACTED_FACT,
        source_id=fact.id,
        content=render_fact_statement(fact),
    )


async def redact_fact(
    session: AsyncSession,
    fact: ExtractedFact,
    *,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
) -> FactRedactionEvent:
    """Post-GA P3-2: hides this fact's content from every shared/rendered
    output (Document composition, search, Ask VocaDox — all go through
    render_fact_statement) while leaving the fact row, its evidence
    links, and this very audit trail fully intact — see
    ExtractedFact.is_redacted's docstring for why that's the "evidence
    chain preserved" the roadmap asks for. A no-op event is still
    recorded if the fact was already redacted, so the audit trail
    reflects every explicit action taken, not just state transitions."""
    fact.is_redacted = True
    event = FactRedactionEvent(
        fact_id=fact.id, redacted=True, reason=reason, actor_user_id=actor_user_id
    )
    session.add(event)
    await session.flush()
    await _resync_search_entry(session, fact)
    return event


async def unredact_fact(
    session: AsyncSession,
    fact: ExtractedFact,
    *,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
) -> FactRedactionEvent:
    fact.is_redacted = False
    event = FactRedactionEvent(
        fact_id=fact.id, redacted=False, reason=reason, actor_user_id=actor_user_id
    )
    session.add(event)
    await session.flush()
    await _resync_search_entry(session, fact)
    return event
