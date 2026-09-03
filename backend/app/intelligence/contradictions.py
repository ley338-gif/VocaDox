"""Contradiction detection (spec §26): a real, testable rule — never
auto-resolves which fact is "true". Only produces a
`ReviewIssue(issue_type=POTENTIAL_CONTRADICTION)` referencing both source
facts; a human decides in the (future, Phase 5) review workflow.

Rule (deliberately narrow and deterministic, not fuzzy text-similarity):
two GENERAL_FACT facts in the same conversation, with the same normalized
(subject, attribute) pair, whose normalized `value` differs, are a
contradiction — this is exactly the shape of the spec's own example
(Ramipril's dose stated as 5mg in one place and 10mg in another).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.intelligence.models import FactCategory


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(frozen=True, slots=True)
class FactForContradictionCheck:
    fact_id: uuid.UUID
    category: str
    subject: str
    attribute: str
    value: str


@dataclass(frozen=True, slots=True)
class Contradiction:
    fact_id_a: uuid.UUID
    fact_id_b: uuid.UUID
    subject: str
    attribute: str
    value_a: str
    value_b: str


def detect_contradictions(
    facts: list[FactForContradictionCheck],
) -> list[Contradiction]:
    """O(n^2) over one conversation's GENERAL_FACT facts — conversations
    are bounded in length, so this is never a scale concern; a smarter
    grouped implementation can replace this later without changing the
    contract."""
    general_facts = [f for f in facts if f.category == FactCategory.GENERAL_FACT.value]
    found: list[Contradiction] = []
    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for i, a in enumerate(general_facts):
        for b in general_facts[i + 1 :]:
            if _normalize(a.subject) != _normalize(b.subject):
                continue
            if _normalize(a.attribute) != _normalize(b.attribute):
                continue
            if _normalize(a.value) == _normalize(b.value):
                continue
            sorted_ids = sorted((a.fact_id, b.fact_id), key=str)
            pair: tuple[uuid.UUID, uuid.UUID] = (sorted_ids[0], sorted_ids[1])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            found.append(
                Contradiction(
                    fact_id_a=a.fact_id,
                    fact_id_b=b.fact_id,
                    subject=a.subject,
                    attribute=a.attribute,
                    value_a=a.value,
                    value_b=b.value,
                )
            )
    return found
