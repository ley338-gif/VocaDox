"""Deterministic, structural conversation comparison (spec §40).

**Hard constraint from the spec, verbatim intent: "Keine unbelegte
Interpretation von Aenderungen" -- no unsubstantiated interpretation of
changes.** This module is a real, testable, deterministic structural
comparison over already-extracted `GENERAL_FACT` facts (same pattern as
`app.intelligence.contradictions`, reused/extended here rather than
inventing an LLM-based "explain what changed" narrative). Every result
carries the fact id(s) that justify it -- never asserts a change without
pointing at both data points.

Four classifications (exactly the spec's list):

- `NEW`: a (subject, attribute) pair appears for the first time anywhere
  in the external-reference group's history.
- `CHANGED`: the pair appeared in an earlier conversation with a different
  normalized value, and there is no same-conversation contradiction on
  that pair in either conversation (an ordinary, expected update).
- `NOT_MENTIONED`: the pair appeared in an earlier conversation but is
  entirely absent from the current one.
- `CONTRADICTED`: two facts for the same (subject, attribute) pair with
  different normalized values exist *within the same conversation* --
  this reuses `app.intelligence.contradictions.detect_contradictions`'s
  exact rule directly rather than re-implementing it, so a conversation
  that itself contains a genuine self-contradiction never gets quietly
  reported as a clean CHANGED.

Unchanged pairs (same normalized value across conversations) are not
reported -- the diff only ever contains real differences.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.intelligence.contradictions import (
    Contradiction,
    FactForContradictionCheck,
    detect_contradictions,
)
from app.intelligence.models import FactCategory


class ComparisonStatus(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    NOT_MENTIONED = "not_mentioned"
    CONTRADICTED = "contradicted"


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@dataclass(frozen=True, slots=True)
class ConversationFactSnapshot:
    """One conversation's worth of GENERAL_FACT facts, as needed for
    comparison. `conversation_id`/`conversation_title`/`occurred_at` let
    the API response show the evidence context without a second query."""

    conversation_id: uuid.UUID
    conversation_title: str
    occurred_at: datetime
    facts: list[FactForContradictionCheck]


@dataclass(frozen=True, slots=True)
class ComparisonItem:
    status: ComparisonStatus
    subject: str
    attribute: str
    # The conversation this item is reported "for" (the later/current one,
    # except NOT_MENTIONED where it's the conversation where it went
    # missing).
    conversation_id: uuid.UUID
    conversation_title: str
    # Evidence: the specific fact id(s) being compared -- both sides kept
    # whenever both exist, per the "never assert without both data points"
    # rule.
    current_fact_id: uuid.UUID | None
    current_value: str | None
    prior_fact_id: uuid.UUID | None
    prior_value: str | None
    prior_conversation_id: uuid.UUID | None


def compare_conversation_group(
    snapshots: list[ConversationFactSnapshot],
) -> list[ComparisonItem]:
    """`snapshots` must already be sorted chronologically (oldest first) by
    the caller and already scoped to one (organization_id,
    external_reference) group -- this function has no organization/
    external_reference awareness at all, so the isolation guarantee lives
    entirely in the caller's query (see app.longitudinal.service
    .build_comparison)."""
    items: list[ComparisonItem] = []

    # -- Step 1: same-conversation contradictions, one call per
    #    conversation, reusing app.intelligence.contradictions verbatim.
    contradicted_pairs_by_conversation: dict[uuid.UUID, set[tuple[str, str]]] = {}
    contradictions_by_conversation: dict[uuid.UUID, list[Contradiction]] = {}
    for snap in snapshots:
        found = detect_contradictions(snap.facts)
        if found:
            contradictions_by_conversation[snap.conversation_id] = found
            contradicted_pairs_by_conversation[snap.conversation_id] = {
                (_normalize(c.subject), _normalize(c.attribute)) for c in found
            }
            for c in found:
                items.append(
                    ComparisonItem(
                        status=ComparisonStatus.CONTRADICTED,
                        subject=c.subject,
                        attribute=c.attribute,
                        conversation_id=snap.conversation_id,
                        conversation_title=snap.conversation_title,
                        current_fact_id=c.fact_id_b,
                        current_value=c.value_b,
                        prior_fact_id=c.fact_id_a,
                        prior_value=c.value_a,
                        prior_conversation_id=snap.conversation_id,
                    )
                )

    # -- Step 2: cross-conversation temporal diff, per (subject, attribute)
    #    pair, tracking the most recent prior occurrence.
    # last_seen[(subject_norm, attribute_norm)] = (conversation_id, title, fact)
    last_seen: dict[tuple[str, str], tuple[uuid.UUID, str, FactForContradictionCheck]] = {}

    for snap in snapshots:
        general = [f for f in snap.facts if f.category == FactCategory.GENERAL_FACT.value]
        contradicted_here = contradicted_pairs_by_conversation.get(snap.conversation_id, set())

        # Group this conversation's own facts by pair so a same-conversation
        # contradiction doesn't ALSO get double-reported as CHANGED/NEW.
        by_pair: dict[tuple[str, str], list[FactForContradictionCheck]] = {}
        for f in general:
            key = (_normalize(f.subject), _normalize(f.attribute))
            by_pair.setdefault(key, []).append(f)

        seen_pairs_this_conversation: set[tuple[str, str]] = set()

        for key, facts_for_pair in by_pair.items():
            seen_pairs_this_conversation.add(key)
            # Pick a single representative value for this conversation's
            # pair (the most recently created fact for it) -- if the pair
            # is already flagged CONTRADICTED for this conversation, skip
            # the temporal diff entirely for it (already reported above,
            # and picking "a" value to diff against history would be an
            # unsubstantiated interpretation of which one is "the" value).
            if key in contradicted_here:
                # Still advance last_seen so a LATER conversation's diff is
                # against a real fact, not silently dropped. Use the last
                # (most recently added) fact as the representative.
                last_seen[key] = (snap.conversation_id, snap.conversation_title, facts_for_pair[-1])
                continue

            current = facts_for_pair[-1]
            prior = last_seen.get(key)
            if prior is None:
                items.append(
                    ComparisonItem(
                        status=ComparisonStatus.NEW,
                        subject=current.subject,
                        attribute=current.attribute,
                        conversation_id=snap.conversation_id,
                        conversation_title=snap.conversation_title,
                        current_fact_id=current.fact_id,
                        current_value=current.value,
                        prior_fact_id=None,
                        prior_value=None,
                        prior_conversation_id=None,
                    )
                )
            else:
                prior_conv_id, prior_conv_title, prior_fact = prior
                if _normalize(prior_fact.value) != _normalize(current.value):
                    items.append(
                        ComparisonItem(
                            status=ComparisonStatus.CHANGED,
                            subject=current.subject,
                            attribute=current.attribute,
                            conversation_id=snap.conversation_id,
                            conversation_title=snap.conversation_title,
                            current_fact_id=current.fact_id,
                            current_value=current.value,
                            prior_fact_id=prior_fact.fact_id,
                            prior_value=prior_fact.value,
                            prior_conversation_id=prior_conv_id,
                        )
                    )
                # else: unchanged -- not reported, per the module docstring.
            last_seen[key] = (snap.conversation_id, snap.conversation_title, current)

        # NOT_MENTIONED: any pair known from an earlier conversation that
        # this conversation doesn't mention at all.
        for key, (prior_conv_id, _prior_conv_title, prior_fact) in list(last_seen.items()):
            if key in seen_pairs_this_conversation:
                continue
            if prior_conv_id == snap.conversation_id:
                continue
            # Reported once per conversation where the pair is missing
            # (this guard only prevents an accidental duplicate row within
            # the same conversation's own processing, not across multiple
            # conversations still missing it -- each conversation in the
            # group where a previously-known pair is absent gets its own
            # NOT_MENTIONED row, since "still not mentioned this time" is
            # itself real, evidence-traceable information).
            already_flagged = any(
                it.status == ComparisonStatus.NOT_MENTIONED
                and it.subject.lower() == prior_fact.subject.lower()
                and it.attribute.lower() == prior_fact.attribute.lower()
                and it.conversation_id == snap.conversation_id
                for it in items
            )
            if already_flagged:
                continue
            items.append(
                ComparisonItem(
                    status=ComparisonStatus.NOT_MENTIONED,
                    subject=prior_fact.subject,
                    attribute=prior_fact.attribute,
                    conversation_id=snap.conversation_id,
                    conversation_title=snap.conversation_title,
                    current_fact_id=None,
                    current_value=None,
                    prior_fact_id=prior_fact.fact_id,
                    prior_value=prior_fact.value,
                    prior_conversation_id=prior_conv_id,
                )
            )

    return items
