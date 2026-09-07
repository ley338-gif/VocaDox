"""Post-GA P1-3: template completeness scoring for a conversation — does
its current set of extracted facts cover what its resolved Template
actually asks for, and are decisions/tasks fully specified (who decided,
who owns it)? Plus speaking-share/longest-monologue from diarization,
per the roadmap's explicit request to surface both together.

Nothing here writes anything — this is a read-only, computed-on-demand
view, same "no new AI Evidence claim, no persisted judgment" posture as
app.analytics.wer (a pure metric, not a generated statement).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.diarization.models import DiarizationSegment
from app.diarization.service import list_speakers
from app.intelligence.models import ExtractedFact, FactCategory, FactReviewStatus, FactStatus
from app.intelligence.rendering import effective_value
from app.intelligence.schemas import NOT_MENTIONED
from app.profiles.resolver import resolve_effective_config
from app.templates.models import Template, TemplateVersion

# A monologue tolerates this much silence between two turns from the same
# speaker before treating it as ended — a deliberate heuristic (real
# "did the floor change" detection would need far more signal than turn
# timestamps alone), disclosed in docs/admin/completeness.md.
_MONOLOGUE_GAP_TOLERANCE_MS = 1500


@dataclass(frozen=True, slots=True)
class CategoryCoverage:
    category: str
    title: str
    covered: bool
    fact_count: int


@dataclass(frozen=True, slots=True)
class SpeakingShare:
    speaker_id: uuid.UUID
    label: str
    speaking_ms: int
    share: float


@dataclass(frozen=True, slots=True)
class MonologueSpan:
    speaker_id: uuid.UUID
    label: str
    start_ms: int
    end_ms: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    template_key: str | None
    template_name: str | None
    template_version_id: uuid.UUID | None
    categories: list[CategoryCoverage]
    category_coverage_ratio: float
    decisions_total: int
    decisions_missing_decided_by: int
    tasks_total: int
    tasks_missing_assignee: int
    overall_score: float
    speaking_shares: list[SpeakingShare]
    longest_monologue: MonologueSpan | None


def _is_not_mentioned(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.upper() == NOT_MENTIONED


async def compute_completeness(
    session: AsyncSession, *, conversation: Conversation
) -> CompletenessResult:
    effective = await resolve_effective_config(session, conversation)
    template_version = await session.get(TemplateVersion, effective.template_version_id)
    template = await session.get(Template, effective.template_id)

    facts_result = await session.execute(
        select(ExtractedFact).where(
            ExtractedFact.conversation_id == conversation.id,
            ExtractedFact.review_status != FactReviewStatus.REMOVED.value,
            ExtractedFact.status != FactStatus.SUPERSEDED.value,
        )
    )
    facts = list(facts_result.scalars().all())

    categories_def = template_version.extraction_categories if template_version is not None else []
    titles_by_category = {
        entry["category"]: entry["title"]
        for entry in (template_version.presentation if template_version is not None else [])
    }
    category_rows: list[CategoryCoverage] = []
    for category_def in categories_def:
        key = category_def["key"]
        matching = [f for f in facts if f.category == key]
        category_rows.append(
            CategoryCoverage(
                category=key,
                title=titles_by_category.get(key, key),
                covered=len(matching) > 0,
                fact_count=len(matching),
            )
        )
    covered_count = sum(1 for c in category_rows if c.covered)
    category_ratio = (covered_count / len(category_rows)) if category_rows else 1.0

    decisions = [f for f in facts if f.category == FactCategory.DECISION.value]
    decisions_missing = sum(
        1 for f in decisions if _is_not_mentioned(effective_value(f).get("decided_by"))
    )
    tasks = [f for f in facts if f.category == FactCategory.TASK.value]
    tasks_missing = sum(1 for f in tasks if _is_not_mentioned(effective_value(f).get("assignee")))

    # Unweighted mean of whichever signals actually apply — a conversation
    # with no decisions isn't penalized for lacking a decision rationale
    # it never had reason to record. Category coverage always applies.
    signals = [category_ratio]
    if decisions:
        signals.append(1 - decisions_missing / len(decisions))
    if tasks:
        signals.append(1 - tasks_missing / len(tasks))
    overall_score = sum(signals) / len(signals)

    speaking_shares, longest_monologue = await _compute_speaking_metrics(
        session, conversation_id=conversation.id
    )

    return CompletenessResult(
        template_key=template.key if template is not None else None,
        template_name=template.name if template is not None else None,
        template_version_id=template_version.id if template_version is not None else None,
        categories=category_rows,
        category_coverage_ratio=category_ratio,
        decisions_total=len(decisions),
        decisions_missing_decided_by=decisions_missing,
        tasks_total=len(tasks),
        tasks_missing_assignee=tasks_missing,
        overall_score=overall_score,
        speaking_shares=speaking_shares,
        longest_monologue=longest_monologue,
    )


async def _compute_speaking_metrics(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> tuple[list[SpeakingShare], MonologueSpan | None]:
    speakers = await list_speakers(session, conversation_id=conversation_id)
    if not speakers:
        return [], None
    label_by_id = {s.id: (s.display_label or s.internal_label) for s in speakers}

    segments_result = await session.execute(
        select(DiarizationSegment)
        .where(DiarizationSegment.speaker_id.in_(label_by_id.keys()))
        .order_by(DiarizationSegment.start_ms)
    )
    segments = list(segments_result.scalars().all())

    speaking_ms: dict[uuid.UUID, int] = defaultdict(int)
    for seg in segments:
        speaking_ms[seg.speaker_id] += seg.end_ms - seg.start_ms
    total_ms = sum(speaking_ms.values())
    shares = [
        SpeakingShare(
            speaker_id=speaker_id,
            label=label_by_id[speaker_id],
            speaking_ms=speaking_ms.get(speaker_id, 0),
            share=(speaking_ms.get(speaker_id, 0) / total_ms) if total_ms else 0.0,
        )
        for speaker_id in label_by_id
    ]

    longest_monologue: MonologueSpan | None = None
    run_speaker: uuid.UUID | None = None
    run_start = 0
    run_end = 0

    def _flush() -> None:
        nonlocal longest_monologue
        if run_speaker is None:
            return
        duration = run_end - run_start
        if longest_monologue is None or duration > longest_monologue.duration_ms:
            longest_monologue = MonologueSpan(
                speaker_id=run_speaker,
                label=label_by_id[run_speaker],
                start_ms=run_start,
                end_ms=run_end,
                duration_ms=duration,
            )

    for seg in segments:
        if run_speaker == seg.speaker_id and seg.start_ms <= run_end + _MONOLOGUE_GAP_TOLERANCE_MS:
            run_end = max(run_end, seg.end_ms)
        else:
            _flush()
            run_speaker = seg.speaker_id
            run_start = seg.start_ms
            run_end = seg.end_ms
    _flush()

    return shares, longest_monologue
