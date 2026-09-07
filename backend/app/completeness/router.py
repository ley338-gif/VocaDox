"""REST endpoint for the template completeness score (post-GA P1-3):
read-only, computed on demand, same conversation-access gate as every
other per-conversation view."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.completeness.schemas import (
    CategoryCoverageResponse,
    CompletenessResponse,
    MonologueSpanResponse,
    SpeakingShareResponse,
)
from app.completeness.service import compute_completeness
from app.conversations.authz import authorize_conversation_access
from app.identity.deps import get_current_user
from app.identity.models import User
from app.platform.db.session import get_session

router = APIRouter(prefix="/conversations", tags=["completeness"])


@router.get("/{conversation_id}/completeness", response_model=CompletenessResponse)
async def get_completeness_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CompletenessResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="fact:read"
    )
    result = await compute_completeness(db, conversation=conversation)
    return CompletenessResponse(
        conversation_id=conversation_id,
        template_key=result.template_key,
        template_name=result.template_name,
        template_version_id=result.template_version_id,
        categories=[CategoryCoverageResponse.model_validate(c) for c in result.categories],
        category_coverage_ratio=result.category_coverage_ratio,
        decisions_total=result.decisions_total,
        decisions_missing_decided_by=result.decisions_missing_decided_by,
        tasks_total=result.tasks_total,
        tasks_missing_assignee=result.tasks_missing_assignee,
        overall_score=result.overall_score,
        speaking_shares=[SpeakingShareResponse.model_validate(s) for s in result.speaking_shares],
        longest_monologue=(
            MonologueSpanResponse.model_validate(result.longest_monologue)
            if result.longest_monologue is not None
            else None
        ),
    )
