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


# Post-GA P3-2: the one shared placeholder every redacted fact renders
# as, everywhere render_fact_statement is used (Document composition,
# search indexing, Ask VocaDox citations) — never the real content, and
# never a placeholder that varies by category (which would itself leak
# information about what kind of thing was hidden).
REDACTED_PLACEHOLDER = "[Geschwärzt]"


def render_fact_statement(fact: ExtractedFact) -> str:
    """Byte-identical rendering for the 3 builtin categories (never
    touched, so every pre-Phase-6/Phase-5 rendered document is unchanged).
    Any other category — i.e. anything a Phase 6 template defines, like
    Meeting's action_item or Medical's symptom/finding — falls through to
    a generic renderer built from whatever keys the fact actually has,
    proving the composer isn't secretly still hardcoded to 3 categories.
    See that fallback's own comment for how it avoids exposing raw field
    names like "description" as visible labels.

    A redacted fact (`fact.is_redacted`) always renders as
    `REDACTED_PLACEHOLDER`, regardless of category — this is the one
    place every "publish/present" consumer (compose_document, search
    indexing, Ask VocaDox) goes through, so blacking it out here blacks
    it out everywhere at once, by construction. The raw `GET .../facts`
    API deliberately never calls this function (see
    app.intelligence.models.ExtractedFact.is_redacted's docstring)."""
    if fact.is_redacted:
        return REDACTED_PLACEHOLDER
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
    # Generic fallback for any category a Template defines that isn't one
    # of the 3 hardcoded ones above (Post-GA medical/meeting/psychotherapy
    # categories included). Every current Template schema (app.templates.
    # seed) puts the fact's actual content in a field named "description"
    # or "name" — that field renders unlabeled, like prose, exactly as a
    # reader expects a sentence to start; only the remaining fields (e.g.
    # onset/severity/dose) get an explicit "label: value" annotation, and
    # only once the extractor actually found a value ('NOT_MENTIONED' is
    # deliberately omitted rather than rendered as noise). Never render a
    # raw field name — "description"/"name" included — as a visible label
    # in the composed document or Kurzfassung.
    excluded = {"certainty", "evidence_segment_sequences"}
    primary_key = "description" if "description" in value else ("name" if "name" in value else None)
    if primary_key is not None:
        primary = value.get(primary_key)
        annotations = [
            f"{key}: {v}"
            for key, v in value.items()
            if key not in excluded and key != primary_key and v not in (None, "", "NOT_MENTIONED")
        ]
        if primary in (None, ""):
            return "; ".join(annotations) if annotations else "(no details)"
        return f"{primary} ({', '.join(annotations)})" if annotations else str(primary)
    parts = [
        f"{key}: {v}"
        for key, v in value.items()
        if key not in excluded and v not in (None, "", "NOT_MENTIONED")
    ]
    return "; ".join(parts) if parts else "(no details)"
