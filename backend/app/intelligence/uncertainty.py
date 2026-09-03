"""Uncertainty classification (spec §25): real, meaningful states derived
from actual signals — never decoration, never a fixed default. Called once
per persisted ExtractedFact, immediately after evidence resolution (see
app.intelligence.service.persist_extraction).

Each rule below is independently testable — see
tests/intelligence/test_uncertainty.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.models import Certainty
from app.intelligence.schemas import NOT_MENTIONED
from app.review.models import ReviewIssueSeverity, UncertaintyCategory

# Below this average linked-segment ASR confidence, a fact is flagged
# LOW_TRANSCRIPTION_CONFIDENCE. Chosen to match the "low-confidence review
# flag" threshold already used for transcript segments themselves
# (app.transcription — see review_flag), not a new arbitrary number.
_LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class UncertaintySignal:
    category: UncertaintyCategory
    severity: ReviewIssueSeverity
    description: str


# A fact whose only supporting evidence is a very short segment (below
# this character count) likely relied on surrounding conversational
# context the extraction pass didn't have access to as a discrete fact —
# flagged MISSING_CONTEXT rather than treated as fully verified.
_MISSING_CONTEXT_CHAR_THRESHOLD = 15


def classify(
    *,
    certainty: Certainty,
    has_evidence: bool,
    avg_segment_confidence: float | None,
    field_values: list[str],
    evidence_text_char_count: int | None = None,
) -> list[UncertaintySignal]:
    """Returns every uncertainty signal that genuinely applies — a single
    fact can carry more than one (e.g. missing evidence AND an incomplete
    field)."""
    signals: list[UncertaintySignal] = []

    if not has_evidence:
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.MISSING_EVIDENCE,
                ReviewIssueSeverity.CRITICAL,
                "No transcript segment could be resolved as evidence for this fact.",
            )
        )

    if certainty == Certainty.UNCLEAR:
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.AMBIGUOUS_TERM,
                ReviewIssueSeverity.MEDIUM,
                "The extraction model marked this fact as unclear/ambiguous.",
            )
        )

    if certainty == Certainty.INCOMPLETE or any(v == NOT_MENTIONED for v in field_values):
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.INCOMPLETE_VALUE,
                ReviewIssueSeverity.LOW,
                "One or more expected fields were not stated in the transcript.",
            )
        )

    if (
        has_evidence
        and certainty == Certainty.STATED
        and evidence_text_char_count is not None
        and evidence_text_char_count < _MISSING_CONTEXT_CHAR_THRESHOLD
    ):
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.MISSING_CONTEXT,
                ReviewIssueSeverity.MEDIUM,
                "The linked evidence segment is too short to independently confirm this fact "
                "without surrounding conversational context.",
            )
        )

    if avg_segment_confidence is not None and avg_segment_confidence < _LOW_CONFIDENCE_THRESHOLD:
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.LOW_TRANSCRIPTION_CONFIDENCE,
                ReviewIssueSeverity.MEDIUM,
                f"Average ASR confidence of linked segments ({avg_segment_confidence:.2f}) is "
                "below the review threshold.",
            )
        )

    if any(
        s.severity in (ReviewIssueSeverity.HIGH, ReviewIssueSeverity.CRITICAL) for s in signals
    ):
        signals.append(
            UncertaintySignal(
                UncertaintyCategory.USER_REVIEW_REQUIRED,
                ReviewIssueSeverity.HIGH,
                "This fact requires human review before it can be treated as verified.",
            )
        )

    return signals
