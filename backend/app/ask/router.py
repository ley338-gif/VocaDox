"""Ask VocaDox REST endpoint (post-GA P1-1). Same authorization shape as
search (`app.search.router`) -- an answer can only ever cite a fact from
a conversation this user could already read directly.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask.models import AskQuery
from app.ask.schemas import AskCitation, AskRequest, AskResponse, AskStatementResponse
from app.ask.service import ask
from app.conversations.authz import can_bypass_team_scope, user_group_ids
from app.conversations.models import Conversation
from app.core.ai_providers import get_llm_provider
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.intelligence.models import ExtractedFact
from app.intelligence.rendering import render_fact_statement
from app.platform.db.session import get_session
from app.providers.llm import LLMProvider

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse, status_code=status.HTTP_201_CREATED)
async def ask_endpoint(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_llm_provider),
    _csrf: None = Depends(require_csrf),
) -> AskResponse:
    from app.identity.rbac import get_user_permissions
    from app.organizations.models import OrganizationMembership

    permissions = await get_user_permissions(db, user.id)
    if "ask:query" not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")

    org_ids: set[uuid.UUID] | None
    if "system:admin" in permissions:
        org_ids = None
    else:
        result = await db.execute(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user.id
            )
        )
        org_ids = {row[0] for row in result.all()}
    group_ids = None if can_bypass_team_scope(permissions) else await user_group_ids(db, user.id)

    query = await ask(
        db,
        question=payload.question,
        organization_ids=org_ids,
        group_ids=group_ids,
        conversation_id=payload.conversation_id,
        provider=provider,
        asked_by_user_id=user.id,
    )
    await db.commit()
    await db.refresh(query)
    return await _to_response(db, query)


@router.get("/{query_id}", response_model=AskResponse)
async def get_ask_query_endpoint(
    query_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> AskResponse:
    query = await db.get(AskQuery, query_id)
    if query is None or query.asked_by_user_id != user.id:
        # 404, never 403 -- never confirms another user's query exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="query not found")
    return await _to_response(db, query)


async def _to_response(db: AsyncSession, query: AskQuery) -> AskResponse:
    fact_ids = {
        uuid.UUID(fid) for stmt in query.answer_statements for fid in stmt.get("fact_ids", [])
    }
    facts_by_id: dict[uuid.UUID, ExtractedFact] = {}
    conversations_by_id: dict[uuid.UUID, Conversation] = {}
    if fact_ids:
        result = await db.execute(select(ExtractedFact).where(ExtractedFact.id.in_(fact_ids)))
        facts_by_id = {f.id: f for f in result.scalars().all()}
        conv_ids = {f.conversation_id for f in facts_by_id.values()}
        if conv_ids:
            conv_result = await db.execute(
                select(Conversation).where(Conversation.id.in_(conv_ids))
            )
            conversations_by_id = {c.id: c for c in conv_result.scalars().all()}

    statements: list[AskStatementResponse] = []
    for stmt in query.answer_statements:
        citations = []
        for fid_str in stmt.get("fact_ids", []):
            fid = uuid.UUID(fid_str)
            fact = facts_by_id.get(fid)
            if fact is None:
                continue  # fact was removed/superseded since this answer was recorded
            conversation = conversations_by_id.get(fact.conversation_id)
            citations.append(
                AskCitation(
                    fact_id=fact.id,
                    conversation_id=fact.conversation_id,
                    conversation_title=conversation.title if conversation else "",
                    category=fact.category,
                    text=render_fact_statement(fact),
                )
            )
        if citations:
            statements.append(AskStatementResponse(text=stmt["text"], citations=citations))

    return AskResponse(
        id=query.id,
        question=query.question,
        statements=statements,
        had_candidate_evidence=query.had_candidate_evidence,
        created_at=query.created_at,
    )
