"""Unit coverage for app.intelligence.rendering.render_fact_statement's
generic fallback -- the renderer used for every Template-defined category
that isn't one of the 3 hardcoded builtins (general_fact/decision/task),
e.g. medical_consultation's symptom/finding/medication. No DB needed: the
function is a pure transformation of an in-memory ExtractedFact.
"""

from __future__ import annotations

import uuid

from app.intelligence.models import ExtractedFact, FactStatus
from app.intelligence.rendering import render_fact_statement


def _fact(category: str, structured_value: dict) -> ExtractedFact:
    return ExtractedFact(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        processing_run_id=None,
        category=category,
        fact_type=category,
        structured_value=structured_value,
        certainty="stated",
        status=FactStatus.VERIFIED.value,
    )


def test_generic_fallback_renders_description_unlabeled_with_unlabeled_annotations() -> None:
    fact = _fact(
        "symptom",
        {"description": "Atemnot", "onset": "bei Treppensteigen", "severity": "besonders"},
    )
    assert render_fact_statement(fact) == "Atemnot (bei Treppensteigen, besonders)"


def test_generic_fallback_renders_name_unlabeled_with_unlabeled_annotations() -> None:
    fact = _fact("medication", {"name": "Ramipril", "dose": "5mg", "frequency": "1x täglich"})
    assert render_fact_statement(fact) == "Ramipril (5mg, 1x täglich)"


def test_generic_fallback_renders_finding_result_unlabeled() -> None:
    fact = _fact("finding", {"description": "Atemgeräusch", "result": "normal"})
    assert render_fact_statement(fact) == "Atemgeräusch (normal)"


def test_generic_fallback_never_shows_any_raw_field_label() -> None:
    symptom = render_fact_statement(
        _fact(
            "symptom",
            {"description": "Husten", "onset": "seit 3 Tagen", "severity": "NOT_MENTIONED"},
        )
    )
    assert "description:" not in symptom
    assert "onset:" not in symptom
    medication = render_fact_statement(_fact("medication", {"name": "Ramipril", "dose": "5mg"}))
    assert "name:" not in medication
    assert "dose:" not in medication


def test_generic_fallback_omits_not_mentioned_annotations() -> None:
    fact = _fact("finding", {"description": "Atemgeräusch normal", "result": "NOT_MENTIONED"})
    assert render_fact_statement(fact) == "Atemgeräusch normal"


def test_generic_fallback_bare_description_has_no_parens() -> None:
    fact = _fact("diagnosis", {"description": "Akute Bronchitis"})
    assert render_fact_statement(fact) == "Akute Bronchitis"


def test_generic_fallback_without_description_or_name_dumps_fields() -> None:
    fact = _fact("agenda_topic", {"topic": "Budget", "outcome": "approved"})
    assert render_fact_statement(fact) == "topic: Budget; outcome: approved"
