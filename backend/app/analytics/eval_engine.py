"""Evaluation Lab comparison mechanism (Phase 8, spec §50).

Runs the SAME synthetic fixture (app.analytics.fixtures) through a real
extraction "subject" (a system prompt + per-category instructions + LLM
provider + generation config) and measures real, defined metrics — never
a mockup table. Deliberately does NOT write to `extracted_facts`/
`fact_evidence`/`review_issues` (those are for real conversations only):
this reuses the exact same schema/prompt-building/contradiction-detection
building blocks `app.intelligence.service.run_extraction` uses, just
without the DB side effects, so a comparison run never pollutes real
conversation data and can be re-run freely.

Never touches training/fine-tuning in any way (process rule: correction
feedback and evaluation are never used to secretly train a model, spec
§38) — this module only ever calls a provider's existing inference API to
*measure* it.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.analytics.fixtures import (
    GOLD_CONTRADICTIONS_EXPECTED,
    GOLD_DECISIONS,
    GOLD_GENERAL_FACTS,
    GOLD_TASKS,
    GOLD_TOTAL_ITEMS,
    SEGMENTS,
)
from app.intelligence.contradictions import FactForContradictionCheck, detect_contradictions
from app.intelligence.prompts import build_prompt_from_instruction, render_transcript
from app.intelligence.schemas import EXTRACTION_CATEGORIES
from app.providers.llm import LLMProvider

_VALID_SEQUENCES = {seq for seq, _ in SEGMENTS}
_TRANSCRIPT_TEXT = render_transcript(SEGMENTS)


@dataclass(frozen=True, slots=True)
class EvalSubject:
    """One side of a comparison. `label` is a short, human-readable,
    non-secret description (e.g. a model identifier or a prompt version
    number) — never conversation content."""

    label: str
    provider: LLMProvider
    temperature: float
    max_tokens: int
    system_prompt: str
    category_instructions: dict[str, str]


@dataclass(slots=True)
class CategoryOutcome:
    category: str
    json_valid: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class EvalResult:
    label: str
    facts_expected: int
    facts_matched: int
    evidence_linkage_rate: float | None
    contradictions_expected: int
    contradictions_detected: int
    json_valid_categories: int
    json_total_categories: int
    latency_seconds: float
    category_outcomes: list[CategoryOutcome]
    error: str | None = None

    def as_public_dict(self) -> dict[str, Any]:
        """What actually gets stored/returned over the API — counts and
        booleans only, structurally incapable of carrying the fixture's
        (synthetic, but still transcript-shaped) text content, matching
        the same discipline every other analytics view in this phase
        follows for real conversation data."""
        return {
            "label": self.label,
            "facts_expected": self.facts_expected,
            "facts_matched": self.facts_matched,
            "evidence_linkage_rate": self.evidence_linkage_rate,
            "contradictions_expected": self.contradictions_expected,
            "contradictions_detected": self.contradictions_detected,
            "json_valid_categories": self.json_valid_categories,
            "json_total_categories": self.json_total_categories,
            "latency_seconds": round(self.latency_seconds, 3),
            "per_category": [
                {
                    "category": c.category,
                    "json_valid": c.json_valid,
                    "item_count": len(c.items),
                    "error": c.error,
                }
                for c in self.category_outcomes
            ],
            "error": self.error,
        }


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in (haystack or "").lower()


def _match_general_facts(items: list[dict[str, Any]]) -> int:
    matched = 0
    for gold in GOLD_GENERAL_FACTS:
        if any(
            _contains(it.get("subject", ""), gold.subject_contains)
            and _contains(it.get("value", ""), gold.value_contains)
            for it in items
        ):
            matched += 1
    return matched


def _match_decisions(items: list[dict[str, Any]]) -> int:
    matched = 0
    for gold in GOLD_DECISIONS:
        if any(_contains(it.get("description", ""), gold.description_contains) for it in items):
            matched += 1
    return matched


def _match_tasks(items: list[dict[str, Any]]) -> int:
    matched = 0
    for gold in GOLD_TASKS:
        if any(
            _contains(it.get("description", ""), gold.description_contains)
            and _contains(it.get("assignee", ""), gold.assignee_contains)
            for it in items
        ):
            matched += 1
    return matched


_MATCHERS = {
    "general_fact": _match_general_facts,
    "decision": _match_decisions,
    "task": _match_tasks,
}


async def run_eval_subject(subject: EvalSubject) -> EvalResult:
    """Runs all three built-in extraction categories (general_fact/
    decision/task — the same categories the "General Conversation"
    template resolves to, see app.templates.schema_builder) against the
    fixture transcript for ONE subject, and computes real metrics. Never
    raises on a provider/schema failure for an individual category — that
    category is recorded as `json_valid=False` with an empty item list, so
    one bad category doesn't abort the whole comparison (matches the
    illustrative table's "JSON Valid" row being measurable per run even
    when a model gets one category wrong)."""
    outcomes: list[CategoryOutcome] = []
    all_items_by_category: dict[str, list[dict[str, Any]]] = {}
    started = time.monotonic()
    run_error: str | None = None

    for category, (schema_cls, item_field, _fact_type) in EXTRACTION_CATEGORIES.items():
        instruction = subject.category_instructions.get(category)
        if instruction is None:
            outcomes.append(
                CategoryOutcome(
                    category=category, json_valid=False, error="no instruction configured"
                )
            )
            all_items_by_category[category] = []
            continue
        prompt = build_prompt_from_instruction(instruction, _TRANSCRIPT_TEXT)
        json_schema = schema_cls.model_json_schema()
        try:
            response = await subject.provider.complete_structured(
                prompt,
                json_schema=json_schema,
                system_prompt=subject.system_prompt,
                temperature=subject.temperature,
                max_tokens=subject.max_tokens,
            )
            raw = json.loads(response.text)
            validated = schema_cls.model_validate(raw)
            items = [item.model_dump() for item in getattr(validated, item_field)]
            outcomes.append(CategoryOutcome(category=category, json_valid=True, items=items))
            all_items_by_category[category] = items
        except Exception as exc:  # noqa: BLE001 - a bad category must not abort the run
            outcomes.append(
                CategoryOutcome(
                    category=category, json_valid=False, error=f"{type(exc).__name__}: {exc}"
                )
            )
            all_items_by_category[category] = []
            if run_error is None:
                run_error = f"category={category}: {type(exc).__name__}"

    elapsed = time.monotonic() - started

    facts_matched = sum(
        _MATCHERS[category](items) for category, items in all_items_by_category.items()
    )

    all_items = [item for items in all_items_by_category.values() for item in items]
    if all_items:
        with_evidence = sum(
            1
            for item in all_items
            if any(
                seq in _VALID_SEQUENCES for seq in item.get("evidence_segment_sequences", [])
            )
        )
        evidence_linkage_rate = with_evidence / len(all_items)
    else:
        evidence_linkage_rate = None

    general_fact_items = all_items_by_category.get("general_fact", [])
    check_inputs = [
        FactForContradictionCheck(
            fact_id=uuid.uuid4(),
            category="general_fact",
            subject=item.get("subject", ""),
            attribute=item.get("attribute", ""),
            value=item.get("value", ""),
        )
        for item in general_fact_items
        if item.get("value") not in (None, "", "NOT_MENTIONED")
    ]
    contradictions_detected = len(detect_contradictions(check_inputs))

    json_valid_categories = sum(1 for o in outcomes if o.json_valid)

    return EvalResult(
        label=subject.label,
        facts_expected=GOLD_TOTAL_ITEMS,
        facts_matched=facts_matched,
        evidence_linkage_rate=evidence_linkage_rate,
        contradictions_expected=GOLD_CONTRADICTIONS_EXPECTED,
        contradictions_detected=contradictions_detected,
        json_valid_categories=json_valid_categories,
        json_total_categories=len(EXTRACTION_CATEGORIES),
        latency_seconds=elapsed,
        category_outcomes=outcomes,
        error=run_error,
    )
