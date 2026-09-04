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
from app.evidence.models import EvidenceType, FactEvidence
from app.intelligence.contradictions import FactForContradictionCheck, detect_contradictions
from app.intelligence.models import Certainty, ExtractedFact, FactCategory, FactStatus
from app.intelligence.prompts import SYSTEM_PROMPT, build_prompt_from_instruction, render_transcript
from app.intelligence.schemas import NOT_MENTIONED
from app.intelligence.uncertainty import classify as classify_uncertainty
from app.profiles.models import ModelProfile
from app.providers.llm import LLMProvider
from app.review.models import ReviewIssue, ReviewIssueType
from app.templates.models import TemplateVersion
from app.templates.schema_builder import ResolvedCategory, resolve_categories
from app.transcription.models import Transcript, TranscriptSegment

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


def _segment_text(segment: TranscriptSegment) -> str:
    return segment.corrected_text or segment.original_text


def _build_transcript_text(segments: list[TranscriptSegment]) -> str:
    pairs = [(s.sequence, _segment_text(s)) for s in segments]
    text = render_transcript(pairs)
    if len(text) <= _MAX_TRANSCRIPT_CHARS:
        return text
    truncated_pairs: list[tuple[int, str]] = []
    total = 0
    for seq, seg_text in pairs:
        line_len = len(seg_text) + 10
        if total + line_len > _MAX_TRANSCRIPT_CHARS:
            break
        truncated_pairs.append((seq, seg_text))
        total += line_len
    return render_transcript(truncated_pairs)


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

    segments = await _load_segments(session, transcript.id)
    segments_by_sequence = {s.sequence: s for s in segments}
    transcript_text = _build_transcript_text(segments)

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
