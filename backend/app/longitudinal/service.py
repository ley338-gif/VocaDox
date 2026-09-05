"""Timeline, comparison orchestration, and Follow-up/Task service (Phase 9).

**Cross-organization isolation, the single most important rule in this
module**: `Conversation.external_reference` is a free-text field two
different organizations may coincidentally share (e.g. both using
sequential case numbers starting at "1"). Every grouping/comparison query
in this module filters on the COMPOUND key
`(organization_id, external_reference)` -- never `external_reference`
alone. `get_timeline`/`build_comparison` both take an explicit
`organization_id` (derived from the caller's authorized conversation, see
app.longitudinal.router) and it is always part of the WHERE clause, never
an afterthought filter applied in Python after a broader query.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.intelligence.contradictions import FactForContradictionCheck
from app.intelligence.models import ExtractedFact, FactCategory
from app.longitudinal.comparison import (
    ComparisonItem,
    ConversationFactSnapshot,
    compare_conversation_group,
)
from app.longitudinal.models import FollowUpSource, FollowUpStatus, FollowUpTask


class InvalidFollowUpTransitionError(ValueError):
    pass


async def get_timeline_conversations(
    session: AsyncSession, *, organization_id: uuid.UUID, external_reference: str
) -> list[Conversation]:
    """Every conversation sharing (organization_id, external_reference),
    oldest first. Both fields are always part of the SQL WHERE clause --
    the compound key that prevents the cross-organization same-reference
    leak described in the module docstring."""
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.external_reference == external_reference,
            Conversation.deleted_at.is_(None),
        )
        .order_by(Conversation.created_at.asc())
    )
    return list(result.scalars().all())


async def _facts_for_conversation(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[FactForContradictionCheck]:
    result = await session.execute(
        select(ExtractedFact).where(
            ExtractedFact.conversation_id == conversation_id,
            ExtractedFact.category == FactCategory.GENERAL_FACT.value,
            ExtractedFact.status != "superseded",
        )
    )
    facts = list(result.scalars().all())
    return [
        FactForContradictionCheck(
            fact_id=f.id,
            category=f.category,
            subject=f.structured_value.get("subject", ""),
            attribute=f.structured_value.get("attribute", ""),
            value=f.structured_value.get("value", ""),
        )
        for f in facts
        if f.structured_value.get("value") not in (None, "", "NOT_MENTIONED")
    ]


async def build_comparison(
    session: AsyncSession, *, organization_id: uuid.UUID, external_reference: str
) -> list[ComparisonItem]:
    """Deterministic comparison across every conversation sharing
    (organization_id, external_reference), oldest-first. See
    app.longitudinal.comparison's module docstring for the classification
    rules -- this function's only job is building the correctly-scoped,
    correctly-ordered input snapshots (the isolation-critical part)."""
    conversations = await get_timeline_conversations(
        session, organization_id=organization_id, external_reference=external_reference
    )
    snapshots: list[ConversationFactSnapshot] = []
    for conv in conversations:
        facts = await _facts_for_conversation(session, conv.id)
        occurred_at = conv.started_at or conv.created_at
        snapshots.append(
            ConversationFactSnapshot(
                conversation_id=conv.id,
                conversation_title=conv.title,
                occurred_at=occurred_at,
                facts=facts,
            )
        )
    return compare_conversation_group(snapshots)


# -- Follow-ups / Tasks -------------------------------------------------


async def sync_ai_extracted_tasks(session: AsyncSession, *, conversation: Conversation) -> int:
    """Idempotently ensure one `FollowUpTask(source=AI_EXTRACTED)` row
    exists per `ExtractedFact(category="task")` on this conversation that
    doesn't have one yet (matched by `source_fact_id`). Safe to call as
    often as needed (e.g. on every task-list read) -- never creates a
    duplicate, never overwrites a task a human has since edited/closed.
    Returns the number of new rows created."""
    result = await session.execute(
        select(ExtractedFact).where(
            ExtractedFact.conversation_id == conversation.id,
            ExtractedFact.category == FactCategory.TASK.value,
            ExtractedFact.status != "superseded",
        )
    )
    task_facts = list(result.scalars().all())
    if not task_facts:
        return 0

    existing_result = await session.execute(
        select(FollowUpTask.source_fact_id).where(
            FollowUpTask.conversation_id == conversation.id,
            FollowUpTask.source == FollowUpSource.AI_EXTRACTED.value,
        )
    )
    existing_fact_ids = {row[0] for row in existing_result.all()}

    created = 0
    for fact in task_facts:
        if fact.id in existing_fact_ids:
            continue
        value = fact.corrected_structured_value or fact.structured_value
        description = value.get("description") or "(no description)"
        assignee = value.get("assignee")
        due_date = value.get("due_date")
        session.add(
            FollowUpTask(
                organization_id=conversation.organization_id,
                conversation_id=conversation.id,
                source=FollowUpSource.AI_EXTRACTED.value,
                source_fact_id=fact.id,
                description=description,
                assignee=assignee if assignee and assignee != "NOT_MENTIONED" else None,
                due_date=due_date if due_date and due_date != "NOT_MENTIONED" else None,
                status=FollowUpStatus.OPEN.value,
            )
        )
        created += 1
    await session.flush()
    return created


async def list_tasks_for_conversation(
    session: AsyncSession, *, conversation: Conversation
) -> list[FollowUpTask]:
    await sync_ai_extracted_tasks(session, conversation=conversation)
    result = await session.execute(
        select(FollowUpTask)
        .where(FollowUpTask.conversation_id == conversation.id)
        .order_by(FollowUpTask.created_at.asc())
    )
    return list(result.scalars().all())


async def list_tasks_for_organizations(
    session: AsyncSession,
    *,
    organization_ids: set[uuid.UUID] | None,
    status_filter: str | None = None,
) -> list[FollowUpTask]:
    """Cross-conversation task listing for the org-wide "Aufgaben" nav
    entry — reads already-persisted FollowUpTask rows directly (no
    per-conversation AI-extraction sync here, unlike
    `list_tasks_for_conversation`; that sync happens when a conversation's
    own Tasks tab is viewed). `organization_ids=None` means system:admin
    (no org filter), matching the scoping convention used by
    `app.conversations.service.list_conversations`."""
    stmt = select(FollowUpTask).order_by(FollowUpTask.created_at.desc())
    if organization_ids is not None:
        stmt = stmt.where(FollowUpTask.organization_id.in_(organization_ids))
    if status_filter:
        stmt = stmt.where(FollowUpTask.status == status_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_user_task(
    session: AsyncSession,
    *,
    conversation: Conversation,
    description: str,
    assignee: str | None,
    due_date: str | None,
    created_by_user_id: uuid.UUID,
) -> FollowUpTask:
    task = FollowUpTask(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        source=FollowUpSource.USER_CREATED.value,
        source_fact_id=None,
        description=description,
        assignee=assignee,
        due_date=due_date,
        status=FollowUpStatus.OPEN.value,
        created_by_user_id=created_by_user_id,
    )
    session.add(task)
    await session.flush()
    return task


_VALID_STATUSES = {s.value for s in FollowUpStatus}


async def update_task_status(
    session: AsyncSession, *, task: FollowUpTask, status: str, updated_by_user_id: uuid.UUID
) -> FollowUpTask:
    if status not in _VALID_STATUSES:
        raise InvalidFollowUpTransitionError(f"invalid status: {status}")
    task.status = status
    task.updated_by_user_id = updated_by_user_id
    await session.flush()
    return task
