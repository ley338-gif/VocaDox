from __future__ import annotations

import uuid

from app.intelligence.contradictions import FactForContradictionCheck, detect_contradictions
from app.intelligence.models import FactCategory


def _fact(
    subject: str,
    attribute: str,
    value: str,
    category: str = FactCategory.GENERAL_FACT.value,
) -> FactForContradictionCheck:
    return FactForContradictionCheck(
        fact_id=uuid.uuid4(), category=category, subject=subject, attribute=attribute, value=value
    )


def test_same_subject_attribute_different_value_is_a_contradiction() -> None:
    # The spec's own Ramipril example: dose stated as 5mg in one place,
    # 10mg in another.
    facts = [
        _fact("Ramipril", "dose", "5mg"),
        _fact("Ramipril", "dose", "10mg"),
    ]
    contradictions = detect_contradictions(facts)
    assert len(contradictions) == 1
    assert contradictions[0].subject == "Ramipril"
    assert {contradictions[0].value_a, contradictions[0].value_b} == {"5mg", "10mg"}


def test_same_value_is_not_a_contradiction() -> None:
    facts = [_fact("Termin", "date", "Montag"), _fact("Termin", "date", "montag")]
    assert detect_contradictions(facts) == []


def test_different_subjects_are_not_compared() -> None:
    facts = [_fact("Ramipril", "dose", "5mg"), _fact("Metformin", "dose", "10mg")]
    assert detect_contradictions(facts) == []


def test_non_general_fact_category_is_ignored() -> None:
    facts = [
        _fact("Ramipril", "dose", "5mg", category="decision"),
        _fact("Ramipril", "dose", "10mg", category="decision"),
    ]
    assert detect_contradictions(facts) == []


def test_three_way_conflict_produces_pairwise_contradictions_without_duplicates() -> None:
    facts = [
        _fact("Ramipril", "dose", "5mg"),
        _fact("Ramipril", "dose", "10mg"),
        _fact("Ramipril", "dose", "7.5mg"),
    ]
    contradictions = detect_contradictions(facts)
    assert len(contradictions) == 3  # 5/10, 5/7.5, 10/7.5 — each pair once
    pairs = {frozenset((c.fact_id_a, c.fact_id_b)) for c in contradictions}
    assert len(pairs) == 3
