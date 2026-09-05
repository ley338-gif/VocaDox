"""REST endpoints for Timeline, Comparison, and Follow-ups/Tasks (Phase 9).

Every route enforces Permission + Organization Membership, matching the
Phase 2/3/4 pattern (`app.conversations.authz`). The two
`/external-references/{ref}/...` endpoints take an explicit
`organization_id` query parameter and verify the caller is a member of
THAT organization (or `system:admin`) -- `external_reference` alone is
never trusted as a scoping key (see app.longitudinal.service's module
docstring for why: two organizations can coincidentally share the same
reference string).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import (
    assert_organization_member_or_admin,
    authorize_conversation_access,
)
from app.conversations.models import Conversation
from app.identity.deps import get_current_user, require_csrf, require_permission
from app.identity.models import User
from app.longitudinal.api_schemas import (
    ComparisonItemResponse,
    ComparisonResponse,
    CreateTaskRequest,
    FollowUpTaskResponse,
    TimelineEntry,
    TimelineResponse,
    UpdateTaskRequest,
)
from app.longitudinal.models import FollowUpTask
from app.longitudinal.service import (
    InvalidFollowUpTransitionError,
    build_comparison,
    create_user_task,
    get_timeline_conversations,
    list_tasks_for_conversation,
    list_tasks_for_organizations,
    update_task_status,
)
from app.platform.db.session import get_session

router = APIRouter(tags=["longitudinal"])

_require_timeline_read = require_permission("timeline:read")


async def _fact_count(db: AsyncSession, conversation_id: uuid.UUID) -> int:
    from app.intelligence.models import ExtractedFact

    result = await db.execute(
        select(ExtractedFact).where(ExtractedFact.conversation_id == conversation_id)
    )
    return len(result.scalars().all())


async def _build_timeline_response(
    db: AsyncSession, *, external_reference: str, conversations: list[Conversation]
) -> TimelineResponse:
    entries = []
    for conv in conversations:
        entries.append(
            TimelineEntry(
                conversation_id=conv.id,
                title=conv.title,
                conversation_type=conv.conversation_type,
                status=conv.status,
                occurred_at=conv.started_at or conv.created_at,
                fact_count=await _fact_count(db, conv.id),
            )
        )
    return TimelineResponse(external_reference=external_reference, conversations=entries)


# -- Timeline / Comparison, reached from a specific conversation ------------


@router.get("/conversations/{conversation_id}/related", response_model=TimelineResponse)
async def get_related_conversations_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="timeline:read"
    )
    if not conversation.external_reference:
        return await _build_timeline_response(
            db, external_reference="", conversations=[conversation]
        )
    conversations = await get_timeline_conversations(
        db,
        organization_id=conversation.organization_id,
        external_reference=conversation.external_reference,
    )
    return await _build_timeline_response(
        db, external_reference=conversation.external_reference, conversations=conversations
    )


# -- Timeline / Comparison, reached by (organization_id, external_reference) --


@router.get("/external-references/{external_reference}/timeline", response_model=TimelineResponse)
async def get_external_reference_timeline_endpoint(
    external_reference: str,
    organization_id: uuid.UUID,
    user: User = Depends(_require_timeline_read),
    db: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    conversations = await get_timeline_conversations(
        db, organization_id=organization_id, external_reference=external_reference
    )
    await record_event(
        db,
        event_type="timeline.viewed",
        user_id=user.id,
        username=user.username,
        event_metadata={
            "organization_id": str(organization_id),
            "conversation_count": len(conversations),
        },
    )
    await db.commit()
    return await _build_timeline_response(
        db, external_reference=external_reference, conversations=conversations
    )


@router.get(
    "/external-references/{external_reference}/comparison", response_model=ComparisonResponse
)
async def get_external_reference_comparison_endpoint(
    external_reference: str,
    organization_id: uuid.UUID,
    user: User = Depends(_require_timeline_read),
    db: AsyncSession = Depends(get_session),
) -> ComparisonResponse:
    await assert_organization_member_or_admin(db, user=user, organization_id=organization_id)
    conversations = await get_timeline_conversations(
        db, organization_id=organization_id, external_reference=external_reference
    )
    items = await build_comparison(
        db, organization_id=organization_id, external_reference=external_reference
    )
    return ComparisonResponse(
        external_reference=external_reference,
        conversation_count=len(conversations),
        items=[ComparisonItemResponse.model_validate(asdict(i)) for i in items],
    )


# -- Follow-ups / Tasks ------------------------------------------------------


@router.get("/tasks", response_model=list[FollowUpTaskResponse])
async def list_tasks_endpoint(
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[FollowUpTaskResponse]:
    """Cross-conversation task list for the org-wide "Aufgaben" nav entry —
    same permission + org-scoping pattern as
    `app.conversations.router.conversation_stats_endpoint`."""
    from app.identity.rbac import get_user_permissions
    from app.organizations.models import OrganizationMembership

    permissions = await get_user_permissions(db, user.id)
    if "task:read" not in permissions:
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

    tasks = await list_tasks_for_organizations(
        db, organization_ids=org_ids, status_filter=status_filter
    )
    return [FollowUpTaskResponse.model_validate(t) for t in tasks]


@router.get("/conversations/{conversation_id}/tasks", response_model=list[FollowUpTaskResponse])
async def list_conversation_tasks_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[FollowUpTaskResponse]:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="task:read"
    )
    tasks = await list_tasks_for_conversation(db, conversation=conversation)
    await db.commit()
    return [FollowUpTaskResponse.model_validate(t) for t in tasks]


@router.post(
    "/conversations/{conversation_id}/tasks",
    response_model=FollowUpTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_task_endpoint(
    conversation_id: uuid.UUID,
    payload: CreateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> FollowUpTaskResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="task:create"
    )
    task = await create_user_task(
        db,
        conversation=conversation,
        description=payload.description,
        assignee=payload.assignee,
        due_date=payload.due_date,
        created_by_user_id=user.id,
    )
    await record_event(
        db,
        event_type="task.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"task_id": str(task.id), "conversation_id": str(conversation_id)},
    )
    await db.commit()
    return FollowUpTaskResponse.model_validate(task)


async def _get_task_and_authorize(
    db: AsyncSession, *, user: User, task_id: uuid.UUID, permission_code: str
) -> FollowUpTask:
    result = await db.execute(select(FollowUpTask).where(FollowUpTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    # Re-derive authorization from the owning conversation -- a task is
    # exactly as sensitive as the conversation it belongs to, never
    # reachable purely by knowing its UUID (same rule as facts/evidence).
    await authorize_conversation_access(
        db, user=user, conversation_id=task.conversation_id, permission_code=permission_code
    )
    return task


@router.patch("/tasks/{task_id}", response_model=FollowUpTaskResponse)
async def update_task_endpoint(
    task_id: uuid.UUID,
    payload: UpdateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> FollowUpTaskResponse:
    task = await _get_task_and_authorize(
        db, user=user, task_id=task_id, permission_code="task:update"
    )
    try:
        task = await update_task_status(
            db, task=task, status=payload.status.value, updated_by_user_id=user.id
        )
    except InvalidFollowUpTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_event(
        db,
        event_type="task.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"task_id": str(task.id), "status": task.status},
    )
    await db.commit()
    await db.refresh(task)
    return FollowUpTaskResponse.model_validate(task)
