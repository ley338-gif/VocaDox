"""Unit tests for the deterministic structural comparison engine (spec
§40). No DB, no LLM — pure function tests over hand-built fact snapshots,
proving the four classifications (NEW/CHANGED/NOT_MENTIONED/CONTRADICTED)
are produced correctly and every result carries both evidence fact ids
where both exist ("Keine unbelegte Interpretation von Aenderungen")."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.intelligence.contradictions import FactForContradictionCheck
from app.longitudinal.comparison import (
    ComparisonStatus,
    ConversationFactSnapshot,
    compare_conversation_group,
)


def _fact(subject: str, attribute: str, value: str) -> FactForContradictionCheck:
    return FactForContradictionCheck(
        fact_id=uuid.uuid4(),
        category="general_fact",
        subject=subject,
        attribute=attribute,
        value=value,
    )


def _snap(conv_id: uuid.UUID, title: str, day: int, facts: list[FactForContradictionCheck]):
    return ConversationFactSnapshot(
        conversation_id=conv_id,
        conversation_title=title,
        occurred_at=datetime(2026, 1, day, tzinfo=UTC),
        facts=facts,
    )


def test_first_occurrence_is_new() -> None:
    conv1 = uuid.uuid4()
    dose_fact = _fact("Ramipril", "dose", "5mg")
    snapshots = [_snap(conv1, "Visit 1", 1, [dose_fact])]

    items = compare_conversation_group(snapshots)

    assert len(items) == 1
    assert items[0].status == ComparisonStatus.NEW
    assert items[0].current_fact_id == dose_fact.fact_id
    assert items[0].current_value == "5mg"
    assert items[0].prior_fact_id is None


def test_changed_value_across_conversations_carries_both_evidence_ids() -> None:
    conv1, conv2 = uuid.uuid4(), uuid.uuid4()
    fact1 = _fact("Ramipril", "dose", "5mg")
    fact2 = _fact("Ramipril", "dose", "10mg")
    snapshots = [
        _snap(conv1, "Visit 1", 1, [fact1]),
        _snap(conv2, "Visit 2", 2, [fact2]),
    ]

    items = compare_conversation_group(snapshots)

    # conv1's fact is NEW, conv2's is CHANGED relative to conv1's.
    statuses = {(i.conversation_id, i.status) for i in items}
    assert (conv1, ComparisonStatus.NEW) in statuses
    changed = next(i for i in items if i.status == ComparisonStatus.CHANGED)
    assert changed.conversation_id == conv2
    assert changed.current_fact_id == fact2.fact_id
    assert changed.current_value == "10mg"
    assert changed.prior_fact_id == fact1.fact_id
    assert changed.prior_value == "5mg"
    assert changed.prior_conversation_id == conv1


def test_unchanged_value_produces_no_item() -> None:
    conv1, conv2 = uuid.uuid4(), uuid.uuid4()
    fact1 = _fact("Ramipril", "dose", "5mg")
    fact2 = _fact("Ramipril", "dose", "5mg")  # identical, different fact row
    snapshots = [
        _snap(conv1, "Visit 1", 1, [fact1]),
        _snap(conv2, "Visit 2", 2, [fact2]),
    ]

    items = compare_conversation_group(snapshots)

    # conv1 -> NEW only; conv2's identical value produces nothing.
    assert len(items) == 1
    assert items[0].conversation_id == conv1
    assert items[0].status == ComparisonStatus.NEW


def test_not_mentioned_when_a_later_conversation_omits_a_known_fact() -> None:
    conv1, conv2 = uuid.uuid4(), uuid.uuid4()
    fact1 = _fact("Ramipril", "dose", "5mg")
    snapshots = [
        _snap(conv1, "Visit 1", 1, [fact1]),
        _snap(conv2, "Visit 2", 2, []),  # dose not discussed this time
    ]

    items = compare_conversation_group(snapshots)

    not_mentioned = [i for i in items if i.status == ComparisonStatus.NOT_MENTIONED]
    assert len(not_mentioned) == 1
    item = not_mentioned[0]
    assert item.conversation_id == conv2
    assert item.prior_fact_id == fact1.fact_id
    assert item.prior_value == "5mg"
    assert item.current_fact_id is None


def test_same_conversation_contradiction_is_reported_as_contradicted() -> None:
    conv1 = uuid.uuid4()
    fact_a = _fact("Ramipril", "dose", "5mg")
    fact_b = _fact("Ramipril", "dose", "10mg")
    snapshots = [_snap(conv1, "Visit 1", 1, [fact_a, fact_b])]

    items = compare_conversation_group(snapshots)

    assert len(items) == 1
    item = items[0]
    assert item.status == ComparisonStatus.CONTRADICTED
    assert item.conversation_id == conv1
    assert {item.current_fact_id, item.prior_fact_id} == {fact_a.fact_id, fact_b.fact_id}


def test_case_and_whitespace_normalization_treats_pairs_as_equal() -> None:
    conv1, conv2 = uuid.uuid4(), uuid.uuid4()
    fact1 = _fact("Ramipril", "Dose", "5mg")
    fact2 = _fact("  ramipril  ", "dose", "5MG")
    snapshots = [
        _snap(conv1, "Visit 1", 1, [fact1]),
        _snap(conv2, "Visit 2", 2, [fact2]),
    ]

    items = compare_conversation_group(snapshots)

    # Normalized subject/attribute match -> conv1 NEW, but normalized value
    # also matches ("5mg" == "5mg" case-insensitively) -> no CHANGED item.
    assert len(items) == 1
    assert items[0].status == ComparisonStatus.NEW


def test_different_subject_attribute_pairs_are_independent() -> None:
    conv1 = uuid.uuid4()
    dose = _fact("Ramipril", "dose", "5mg")
    frequency = _fact("Ramipril", "frequency", "once daily")
    snapshots = [_snap(conv1, "Visit 1", 1, [dose, frequency])]

    items = compare_conversation_group(snapshots)

    assert len(items) == 2
    assert all(i.status == ComparisonStatus.NEW for i in items)
    subjects_attrs = {(i.subject, i.attribute) for i in items}
    assert subjects_attrs == {("Ramipril", "dose"), ("Ramipril", "frequency")}
