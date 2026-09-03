from __future__ import annotations

from app.intelligence.models import Certainty
from app.intelligence.uncertainty import classify
from app.review.models import ReviewIssueSeverity, UncertaintyCategory


def test_missing_evidence_is_critical() -> None:
    signals = classify(
        certainty=Certainty.STATED,
        has_evidence=False,
        avg_segment_confidence=None,
        field_values=["Ramipril", "5mg"],
    )
    categories = {s.category for s in signals}
    assert UncertaintyCategory.MISSING_EVIDENCE in categories
    critical = [s for s in signals if s.category == UncertaintyCategory.MISSING_EVIDENCE][0]
    assert critical.severity == ReviewIssueSeverity.CRITICAL
    # Missing evidence is severe enough to also trigger the rollup flag.
    assert UncertaintyCategory.USER_REVIEW_REQUIRED in categories


def test_fully_stated_fact_with_evidence_has_no_signals() -> None:
    signals = classify(
        certainty=Certainty.STATED,
        has_evidence=True,
        avg_segment_confidence=0.95,
        field_values=["Ramipril", "5mg"],
        evidence_text_char_count=200,
    )
    assert signals == []


def test_unclear_certainty_flags_ambiguous_term() -> None:
    signals = classify(
        certainty=Certainty.UNCLEAR,
        has_evidence=True,
        avg_segment_confidence=0.9,
        field_values=["something"],
        evidence_text_char_count=100,
    )
    assert any(s.category == UncertaintyCategory.AMBIGUOUS_TERM for s in signals)


def test_not_mentioned_field_value_flags_incomplete() -> None:
    signals = classify(
        certainty=Certainty.STATED,
        has_evidence=True,
        avg_segment_confidence=0.9,
        field_values=["Send documents", "NOT_MENTIONED", "NOT_MENTIONED"],
        evidence_text_char_count=100,
    )
    assert any(s.category == UncertaintyCategory.INCOMPLETE_VALUE for s in signals)


def test_low_transcription_confidence_is_flagged() -> None:
    signals = classify(
        certainty=Certainty.STATED,
        has_evidence=True,
        avg_segment_confidence=0.3,
        field_values=["x"],
        evidence_text_char_count=100,
    )
    assert any(s.category == UncertaintyCategory.LOW_TRANSCRIPTION_CONFIDENCE for s in signals)


def test_short_evidence_text_flags_missing_context() -> None:
    signals = classify(
        certainty=Certainty.STATED,
        has_evidence=True,
        avg_segment_confidence=0.95,
        field_values=["ja"],
        evidence_text_char_count=2,
    )
    assert any(s.category == UncertaintyCategory.MISSING_CONTEXT for s in signals)
