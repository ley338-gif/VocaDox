"""Deterministic, human-readable rendering of one `ExtractedFact` into a
single line of text. Shared by `app.documents.service.compose_document`
(one statement per fact in a Document section) and
`app.search.service`-indexed content (post-GA P0-1) -- both need exactly
the same "what does this fact actually say" text, so it lives here once
rather than being duplicated per consumer.
"""

from __future__ import annotations

from typing import Any

from app.intelligence.models import ExtractedFact, FactCategory, FactReviewStatus


def effective_value(fact: ExtractedFact) -> dict[str, Any]:
    """A human CORRECTED value always wins over the original LLM output —
    the original is never discarded (still on `structured_value`), just
    superseded for rendering purposes. See FactReviewStatus's docstring."""
    if fact.review_status == FactReviewStatus.CORRECTED.value and fact.corrected_structured_value:
        return fact.corrected_structured_value
    return fact.structured_value


def render_fact_statement(fact: ExtractedFact) -> str:
    """Byte-identical rendering for the 3 builtin categories (never
    touched, so every pre-Phase-6/Phase-5 rendered document is unchanged).
    Any other category — i.e. anything a Phase 6 template defines, like
    Meeting's agenda_topic/action_item — falls through to a generic
    "field: value" renderer built from whatever keys the fact actually
    has, proving the composer isn't secretly still hardcoded to 3
    categories."""
    value = effective_value(fact)
    keys = set(value.keys())
    if fact.category == FactCategory.GENERAL_FACT.value and keys <= {
        "subject", "attribute", "value", "certainty", "evidence_segment_sequences",
    }:
        subject = value.get("subject", "?")
        attribute = value.get("attribute", "?")
        return f"{subject} — {attribute}: {value.get('value', '?')}"
    if fact.category == FactCategory.DECISION.value and keys <= {
        "description", "decided_by", "certainty", "evidence_segment_sequences",
    }:
        return str(value.get("description", "?"))
    if fact.category == FactCategory.TASK.value and keys <= {
        "description", "assignee", "due_date", "certainty", "evidence_segment_sequences",
    }:
        return (
            f"{value.get('description', '?')} "
            f"(assignee: {value.get('assignee', 'not mentioned')}, "
            f"due: {value.get('due_date', 'not mentioned')})"
        )
    parts = [
        f"{key}: {v}"
        for key, v in value.items()
        if key not in ("certainty", "evidence_segment_sequences") and v not in (None, "")
    ]
    return "; ".join(parts) if parts else "(no details)"
