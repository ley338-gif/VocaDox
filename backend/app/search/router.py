"""Cross-conversation search REST endpoint (post-GA P0-1). Same
authorization shape as `GET /conversations` (`app.conversations.router
.list_conversations_endpoint`) -- a search result is exactly as visible
as the conversation it belongs to, never a side channel around
`conversation:read`/team scoping.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.authz import can_bypass_team_scope, user_group_ids
from app.conversations.models import Conversation
from app.identity.deps import get_current_user
from app.identity.models import User
from app.platform.db.session import get_session
from app.search.schemas import SearchResponse, SearchResultResponse
from app.search.service import search_entries

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search_endpoint(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SearchResponse:
    from app.identity.rbac import get_user_permissions
    from app.organizations.models import OrganizationMembership

    permissions = await get_user_permissions(db, user.id)
    if "conversation:read" not in permissions:
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

    hits, total = await search_entries(
        db, query=q, organization_ids=org_ids, group_ids=group_ids, limit=limit, offset=offset
    )

    conversation_ids = {hit.entry.conversation_id for hit in hits}
    titles: dict[uuid.UUID, str] = {}
    if conversation_ids:
        result = await db.execute(
            select(Conversation.id, Conversation.title).where(
                Conversation.id.in_(conversation_ids)
            )
        )
        titles = {row[0]: row[1] for row in result.all()}

    return SearchResponse(
        items=[
            SearchResultResponse(
                conversation_id=hit.entry.conversation_id,
                conversation_title=titles.get(hit.entry.conversation_id, ""),
                source_type=hit.entry.source_type,
                source_id=hit.entry.source_id,
                snippet=hit.snippet,
                rank=hit.rank,
                updated_at=hit.entry.updated_at,
            )
            for hit in hits
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
