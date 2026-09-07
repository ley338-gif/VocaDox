"""Ask VocaDox orchestration (post-GA P1-1): search for candidate facts,
ask the LLM to answer using only those, then re-verify every citation
server-side before anything reaches the caller. This is the interactive
counterpart to `app.documents.service.compose_document` -- same
principle (never generate a claim without a traceable fact_ids link),
different trigger (a question, not "compose the whole document").
"""

from __future__ import annotations

import json
import uuid

import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.models import AskQuery
from app.ask.prompts import SYSTEM_PROMPT, build_prompt
from app.ask.schemas import AskLLMResponse
from app.conversations.models import Conversation
from app.intelligence.models import ExtractedFact, FactReviewStatus, FactStatus
from app.intelligence.rendering import render_fact_statement
from app.providers.llm import LLMProvider
from app.search.models import SearchSourceType
from app.search.service import search_entries

# How many candidate facts to offer the model per question -- generous
# enough to answer a real question, small enough to stay well inside any
# reasonable context window (this is a handful of short fact statements,
# not a transcript).
_MAX_CANDIDATE_FACTS = 25


async def ask(
    session: AsyncSession,
    *,
    question: str,
    organization_ids: set[uuid.UUID] | None,
    group_ids: set[uuid.UUID] | None,
    conversation_id: uuid.UUID | None,
    provider: LLMProvider,
    asked_by_user_id: uuid.UUID | None,
) -> AskQuery:
    hits, _total = await search_entries(
        session,
        query=question,
        organization_ids=organization_ids,
        group_ids=group_ids,
        limit=_MAX_CANDIDATE_FACTS,
    )
    fact_hits = [h for h in hits if h.entry.source_type == SearchSourceType.EXTRACTED_FACT.value]
    if conversation_id is not None:
        fact_hits = [h for h in fact_hits if h.entry.conversation_id == conversation_id]

    candidate_facts: dict[uuid.UUID, ExtractedFact] = {}
    if fact_hits:
        result = await session.execute(
            select(ExtractedFact).where(
                ExtractedFact.id.in_({h.entry.source_id for h in fact_hits}),
                ExtractedFact.review_status != FactReviewStatus.REMOVED.value,
                ExtractedFact.status != FactStatus.SUPERSEDED.value,
            )
        )
        for fact in result.scalars().all():
            candidate_facts[fact.id] = fact

    verified_statements: list[dict] = []
    if candidate_facts:
        prompt = build_prompt(
            question=question,
            facts=[(str(fid), render_fact_statement(f)) for fid, f in candidate_facts.items()],
        )
        response = await provider.complete_structured(
            prompt,
            json_schema=AskLLMResponse.model_json_schema(),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=1024,
        )
        verified_statements = _verify_statements(response.text, candidate_facts)

    record = AskQuery(
        organization_id=await _resolve_organization_id(
            session, conversation_id=conversation_id, candidate_facts=candidate_facts
        ),
        asked_by_user_id=asked_by_user_id,
        conversation_id=conversation_id,
        question=question,
        answer_statements=verified_statements,
        had_candidate_evidence=bool(candidate_facts),
    )
    session.add(record)
    await session.flush()
    return record


def _verify_statements(
    raw_response_text: str, candidate_facts: dict[uuid.UUID, ExtractedFact]
) -> list[dict]:
    """The actual enforcement point: a statement survives ONLY if it cites
    at least one fact_id, and every fact_id it cites is a real id from
    `candidate_facts` (the exact, already-authorized set offered to the
    model -- never re-trusts an id the model merely claims). Anything
    else -- malformed JSON, an empty citation list, a hallucinated id --
    is silently dropped, never surfaced as if it were a real answer."""
    try:
        parsed = AskLLMResponse.model_validate(json.loads(raw_response_text))
    except (json.JSONDecodeError, pydantic.ValidationError):
        return []

    verified: list[dict] = []
    for statement in parsed.statements:
        if not statement.text.strip() or not statement.fact_ids:
            continue
        try:
            cited_ids = {uuid.UUID(fid) for fid in statement.fact_ids}
        except ValueError:
            continue
        if not cited_ids <= candidate_facts.keys():
            continue
        verified.append({"text": statement.text, "fact_ids": [str(fid) for fid in cited_ids]})
    return verified


async def _resolve_organization_id(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID | None,
    candidate_facts: dict[uuid.UUID, ExtractedFact],
) -> uuid.UUID | None:
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is not None:
            return conversation.organization_id
    if candidate_facts:
        any_fact = next(iter(candidate_facts.values()))
        conversation = await session.get(Conversation, any_fact.conversation_id)
        if conversation is not None:
            return conversation.organization_id
    # No scope and no evidence found -- still a real, auditable query
    # (had_candidate_evidence=False records exactly that); never guessed
    # onto an arbitrary one of the asker's possibly-several organizations.
    return None


async def get_ask_query(session: AsyncSession, query_id: uuid.UUID) -> AskQuery | None:
    return await session.get(AskQuery, query_id)
