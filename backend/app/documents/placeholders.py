"""Placeholder substitution for a "freeform" `TemplateVersion.document_body`
(post-GA — see app.templates.models's docstring). Deliberately its own
module rather than inline in app.documents.service, matching this
codebase's existing "one small module per genuinely separate concern"
style (e.g. app.intelligence.rendering).

Syntax: `[<category_key>_<1-based-index>]`, e.g. `[decision_1]`,
`[diagnosis_2]` — the index is the fact's position within that category's
facts for this conversation, ordered exactly like
app.documents.service.compose_document's existing category grouping
(`created_at.asc()`). A category key may itself contain underscores
(e.g. "general_fact"), so the regex is greedy on the category group and
backtracks to find the final `_<digits>]`.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from app.intelligence.models import ExtractedFact
from app.intelligence.rendering import render_fact_statement

_PLACEHOLDER_RE = re.compile(r"\[([a-zA-Z0-9]+(?:_[a-zA-Z0-9]+)*)_(\d+)\]")


def group_facts_by_category(facts: list[ExtractedFact]) -> dict[str, list[ExtractedFact]]:
    grouped: dict[str, list[ExtractedFact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.category].append(fact)
    return grouped


def missing_placeholder_fallback(category: str, index: int) -> str:
    """Honest, non-fabricated stand-in for a placeholder with no matching
    fact for THIS conversation (e.g. the template references `[decision_2]`
    but only one decision was extracted). Deliberately a distinct string
    from `app.intelligence.prompts.NOT_MENTIONED` — that means "the model
    looked at the transcript and it wasn't said"; this means "the letter
    template references a fact that doesn't exist here at all". Includes
    the token itself so a reviewer can immediately see which placeholder
    had no match."""
    return f"[nicht erfasst: {category}_{index}]"


def substitute_placeholders(
    body: str, facts_by_category: dict[str, list[ExtractedFact]]
) -> tuple[str, list[uuid.UUID]]:
    """Returns `(substituted_text, fact_ids_actually_substituted)`. Every
    resolved placeholder renders via `render_fact_statement` (the same
    deterministic, redaction-aware renderer every other document consumer
    uses) and records that fact's id; an unresolved placeholder (unknown
    category, or an index beyond the available facts) renders
    `missing_placeholder_fallback` and contributes no fact_id — so the
    returned fact_id list is always exactly the evidence that's really
    present in the text, matching this codebase's evidence-chain
    invariant (every DocumentRevision statement's fact_ids must be real)."""
    used_fact_ids: list[uuid.UUID] = []

    def _replace(match: re.Match[str]) -> str:
        category, index_str = match.group(1), match.group(2)
        index = int(index_str)
        items = facts_by_category.get(category, [])
        position = index - 1
        if 0 <= position < len(items):
            fact = items[position]
            used_fact_ids.append(fact.id)
            return render_fact_statement(fact)
        return missing_placeholder_fallback(category, index)

    substituted = _PLACEHOLDER_RE.sub(_replace, body)
    return substituted, used_fact_ids
