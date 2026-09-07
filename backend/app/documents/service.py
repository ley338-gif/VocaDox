"""Document composition, correction (via Review Wizard resolution), and
approval — the Phase 5 core. See module docstrings on
app.documents.models for the domain shapes this operates on.

Composition (`compose_document`) is the spec §23 pipeline's final step:

    Transcript -> Structured Facts -> Evidence Mapping -> Schema
    Validation -> Consistency Checks -> Contradictions -> Review Issues
    -> Document Composition

It is a deterministic, template-free rendering of the conversation's
*current* facts (excluding any a human REMOVED, preferring a human's
CORRECTED value over the original) into a document — never an LLM
"write a report" call (spec's explicitly rejected architecture). Every
statement it produces carries the `fact_ids` it came from, so a reader can
always trace it back through `fact_evidence` to the exact transcript
segment (docs/architecture/domain-model.md's Ramipril chain).

Deliberate deviation from every prior Phase 3/4 processing stage,
documented in `docs/architecture/adr/0027-synchronous-document-composition.md`:
composition runs synchronously inside the HTTP request instead of via the
ProcessingJob/worker queue. Every prior stage (NORMALIZE/TRANSCRIBE/
DIARIZE/ALIGN/EXTRACT) calls into a slow, blocking external provider
(ffmpeg, an ASR/diarization model, an LLM) and MUST NOT run inline in a
request handler for that reason. Composition calls no provider at all —
it is a pure, sub-millisecond transformation of already-persisted rows —
so the "never inline in a request handler" rule's actual justification
(don't block the event loop / the request worker pool on slow I/O) does
not apply, and routing it through the async job machinery would only add
latency and an extra round trip for the frontend with no real benefit.
It is still an explicit, human-triggered action (`POST .../document/
compose`), never automatic — matching spec's "explicit trigger, not
automatic" principle exactly, and still records a `ProcessingRun` for
provenance like every other stage.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.documents.models import Document, DocumentRevision, DocumentRevisionStatus
from app.documents.state_machine import transition
from app.identity.models import User
from app.intelligence.models import (
    ExtractedFact,
    FactCategory,
    FactCorrection,
    FactReviewStatus,
    FactStatus,
)
from app.intelligence.rendering import render_fact_statement
from app.platform.version import APPLICATION_VERSION
from app.processing.models import ProcessingRun, RunStatus, RunType
from app.profiles.resolver import NoSystemDefaultProfileError, resolve_effective_config
from app.review.models import ReviewIssue, ReviewIssueResolution, ReviewIssueStatus
from app.search.models import SearchSourceType
from app.search.service import delete_search_entry, upsert_search_entry
from app.templates.models import TemplateVersion

# Fallback presentation used only if no TemplateVersion can be resolved at
# all (e.g. a fresh test DB with no Phase 6 seed applied) — identical to
# Phase 5's hardcoded mapping, so behavior is unchanged in that edge case.
_FALLBACK_PRESENTATION = [
    {"category": FactCategory.GENERAL_FACT.value, "title": "General Facts"},
    {"category": FactCategory.DECISION.value, "title": "Decisions"},
    {"category": FactCategory.TASK.value, "title": "Tasks & Follow-Ups"},
]

# Severities that block progressing a document to APPROVED (spec §27:
# "High/Critical severity review issues can block approval — implement
# this as a real, enforced check, not decoration").
_BLOCKING_SEVERITIES = {"high", "critical"}


class ApprovalBlockedError(Exception):
    def __init__(self, blocking_issue_ids: list[str]) -> None:
        super().__init__(
            f"{len(blocking_issue_ids)} unresolved high/critical review issue(s) block approval"
        )
        self.blocking_issue_ids = blocking_issue_ids


class DocumentNotComposableError(ValueError):
    pass


async def _resolve_template_version(
    session: AsyncSession, conversation_id: uuid.UUID
) -> TemplateVersion | None:
    from app.conversations.models import Conversation

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:  # pragma: no cover - FK integrity guards this in practice
        return None
    try:
        effective = await resolve_effective_config(session, conversation)
    except NoSystemDefaultProfileError:
        return None
    return await session.get(TemplateVersion, effective.template_version_id)


async def _open_blocking_issues(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> list[ReviewIssue]:
    result = await session.execute(
        select(ReviewIssue).where(
            ReviewIssue.conversation_id == conversation_id,
            ReviewIssue.status == ReviewIssueStatus.OPEN.value,
            ReviewIssue.severity.in_(_BLOCKING_SEVERITIES),
        )
    )
    return list(result.scalars().all())


async def compose_document(
    session: AsyncSession, *, conversation_id: uuid.UUID, requested_by: User
) -> Document:
    """Explicit-trigger composition (`POST /conversations/{id}/document/
    compose`). Always creates a NEW DocumentRevision — never mutates an
    existing one (spec §31), so re-composing after a correction or new
    extraction run is always safe, even against an already-APPROVED
    document (the approved revision is untouched; a fresh revision starts
    the review cycle over)."""
    result = await session.execute(
        select(ExtractedFact)
        .where(
            ExtractedFact.conversation_id == conversation_id,
            ExtractedFact.review_status != FactReviewStatus.REMOVED.value,
            ExtractedFact.status != FactStatus.SUPERSEDED.value,
        )
        .order_by(ExtractedFact.category.asc(), ExtractedFact.created_at.asc())
    )
    facts = list(result.scalars().all())

    # Phase 6: presentation (section order/titles) comes from the
    # conversation's effective Template — see app.profiles.resolver. Falls
    # back to Phase 5's exact hardcoded 3-category presentation if no
    # ProcessingProfile/Template can be resolved at all (e.g. a bare test
    # DB with no Phase 6 seed applied), so behavior for that edge case is
    # unchanged.
    template_version = await _resolve_template_version(session, conversation_id)
    presentation = (
        template_version.presentation if template_version is not None else _FALLBACK_PRESENTATION
    )
    known_categories = {p["category"] for p in presentation}
    # A fact whose category isn't in the resolved template's presentation
    # (e.g. facts left over from an earlier extraction run under a
    # different template) still gets a section — appended at the end,
    # titled from the raw category string — so a document composition
    # never silently drops a real, non-removed fact.
    extra_categories = sorted({f.category for f in facts} - known_categories)
    full_presentation = list(presentation) + [
        {"category": c, "title": c.replace("_", " ").title()} for c in extra_categories
    ]

    sections: list[dict[str, Any]] = []
    text_lines: list[str] = []
    for entry in full_presentation:
        category = entry["category"]
        title = entry["title"]
        category_facts = [f for f in facts if f.category == category]
        if not category_facts:
            continue
        statements = [
            {"text": render_fact_statement(f), "fact_ids": [str(f.id)]} for f in category_facts
        ]
        sections.append({"category": category, "title": title, "statements": statements})
        text_lines.append(f"## {title}")
        text_lines.extend(f"- {s['text']}" for s in statements)
        text_lines.append("")

    blocking = await _open_blocking_issues(session, conversation_id=conversation_id)
    new_status = (
        DocumentRevisionStatus.REVIEW_REQUIRED
        if blocking
        else DocumentRevisionStatus.READY_FOR_APPROVAL
    )

    document_result = await session.execute(
        select(Document).where(Document.conversation_id == conversation_id)
    )
    document = document_result.scalar_one_or_none()
    created_document = False
    if document is None:
        document = Document(
            conversation_id=conversation_id, status=DocumentRevisionStatus.DRAFT.value
        )
        session.add(document)
        await session.flush()
        created_document = True

    max_revision_result = await session.execute(
        select(DocumentRevision.revision_number)
        .where(DocumentRevision.document_id == document.id)
        .order_by(DocumentRevision.revision_number.desc())
    )
    last_number = max_revision_result.scalars().first() or 0

    # Validate the transition against the state machine using the current
    # document status as "current" — a fresh DRAFT->{REVIEW_REQUIRED,
    # READY_FOR_APPROVAL} or a re-compose from any non-APPROVED state is
    # always allowed; re-composing after APPROVED intentionally restarts
    # at the target status directly (equivalent to DRAFT immediately
    # advancing), never mutating the approved row.
    current_status = DocumentRevisionStatus(document.status)
    effective_current = (
        DocumentRevisionStatus.DRAFT
        if current_status == DocumentRevisionStatus.APPROVED
        else current_status
    )
    validated_status = transition(effective_current, new_status)

    run = ProcessingRun(
        conversation_id=conversation_id,
        source_media_id=await _resolve_source_media_id(session, conversation_id),
        run_type=RunType.COMPOSITION.value,
        status=RunStatus.RUNNING.value,
        provider="vocadox-composition",
        model="deterministic-template-v1",
        application_version=APPLICATION_VERSION,
        configuration_snapshot={"fact_count": len(facts), "blocking_issue_count": len(blocking)},
    )
    session.add(run)
    await session.flush()

    revision = DocumentRevision(
        document_id=document.id,
        revision_number=last_number + 1,
        structured_content=sections,
        rendered_text="\n".join(text_lines).strip() or "(no facts to compose)",
        status=validated_status.value,
        blocking_issue_ids=[str(i.id) for i in blocking],
        created_by_user_id=requested_by.id,
        template_version_id=template_version.id if template_version is not None else None,
        document_layout=(
            template_version.document_layout if template_version is not None else "sections"
        ),
    )
    session.add(revision)
    await session.flush()

    document.current_revision_id = revision.id
    document.status = validated_status.value
    await session.flush()

    from app.conversations.models import Conversation

    conversation = await session.get(Conversation, conversation_id)
    assert conversation is not None
    # Keyed on the Document id (never the revision id) so re-composing
    # replaces this one entry instead of accumulating a stale one per
    # past revision -- see SearchEntry's module docstring.
    await upsert_search_entry(
        session,
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        group_id=conversation.group_id,
        source_type=SearchSourceType.DOCUMENT,
        source_id=document.id,
        content=revision.rendered_text,
    )

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    run.raw_output = {"revision_id": str(revision.id), "section_count": len(sections)}
    await session.flush()

    await record_event(
        session,
        event_type="document.created" if created_document else "document.composed",
        user_id=requested_by.id,
        event_metadata={
            "conversation_id": str(conversation_id),
            "document_id": str(document.id),
            "revision_id": str(revision.id),
            "revision_number": revision.revision_number,
            "status": validated_status.value,
            "fact_count": len(facts),
        },
    )
    return document


async def _resolve_source_media_id(session: AsyncSession, conversation_id: uuid.UUID) -> uuid.UUID:
    from app.media.models import MediaAsset, MediaKind

    result = await session.execute(
        select(MediaAsset.id)
        .where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.SOURCE_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc())
    )
    media_id = result.scalars().first()
    if media_id is None:
        raise DocumentNotComposableError("no source audio for this conversation")
    return media_id


async def resolve_review_issue(
    session: AsyncSession,
    *,
    issue: ReviewIssue,
    fact: ExtractedFact,
    action: ReviewIssueResolution,
    corrected_value: dict[str, Any] | None,
    resolved_by: User,
) -> None:
    """Apply one Review Wizard decision (spec §28: Confirm/Correct/Remove)
    to `fact`, then close `issue`. Never overwrites `structured_value` —
    a CORRECT action only ever populates `corrected_structured_value`
    (plus a FactCorrection audit row), matching the non-destructive
    correction pattern Phase 3 established for transcript segments."""
    now = datetime.now(UTC)

    if action == ReviewIssueResolution.CONFIRMED:
        fact.review_status = FactReviewStatus.CONFIRMED.value
    elif action == ReviewIssueResolution.REMOVED:
        fact.review_status = FactReviewStatus.REMOVED.value
        await delete_search_entry(
            session, source_type=SearchSourceType.EXTRACTED_FACT, source_id=fact.id
        )
    elif action == ReviewIssueResolution.CORRECTED:
        if not corrected_value:
            raise ValueError("corrected_value is required for a CORRECT action")
        session.add(
            FactCorrection(
                fact_id=fact.id,
                previous_structured_value=fact.corrected_structured_value or fact.structured_value,
                new_structured_value=corrected_value,
                corrected_by_user_id=resolved_by.id,
            )
        )
        fact.corrected_structured_value = corrected_value
        fact.review_status = FactReviewStatus.CORRECTED.value
    else:  # pragma: no cover - exhaustive StrEnum, defensive
        raise ValueError(f"unknown resolution action: {action!r}")

    fact.reviewed_by_user_id = resolved_by.id
    fact.reviewed_at = now
    await session.flush()

    if action == ReviewIssueResolution.CORRECTED:
        from app.conversations.models import Conversation

        conversation = await session.get(Conversation, issue.conversation_id)
        assert conversation is not None
        await upsert_search_entry(
            session,
            conversation_id=conversation.id,
            organization_id=conversation.organization_id,
            group_id=conversation.group_id,
            source_type=SearchSourceType.EXTRACTED_FACT,
            source_id=fact.id,
            content=render_fact_statement(fact),
        )

    issue.status = ReviewIssueStatus.RESOLVED.value
    issue.resolved_status = action.value
    issue.resolved_fact_id = str(fact.id)
    issue.resolved_by_user_id = resolved_by.id
    issue.resolved_at = now
    await session.flush()

    await record_event(
        session,
        event_type="review_issue.resolved",
        user_id=resolved_by.id,
        event_metadata={
            "conversation_id": str(issue.conversation_id),
            "review_issue_id": str(issue.id),
            "fact_id": str(fact.id),
            "resolution": action.value,
        },
    )
    if action == ReviewIssueResolution.CORRECTED:
        await record_event(
            session,
            event_type="document.corrected",
            user_id=resolved_by.id,
            event_metadata={
                "conversation_id": str(issue.conversation_id),
                "fact_id": str(fact.id),
            },
        )


async def approve_document(
    session: AsyncSession, *, document: Document, conversation_id: uuid.UUID, approved_by: User
) -> Document:
    """Only ever reachable from a route requiring `document:approve` —
    **the AI never calls this**. Blocks (raises ApprovalBlockedError) if
    any HIGH/CRITICAL review issue is still OPEN, and refuses
    (DocumentNotComposableError) unless the current revision is already
    READY_FOR_APPROVAL — approval never skips review."""
    if document.current_revision_id is None:
        raise DocumentNotComposableError("document has no revision to approve — compose it first")

    revision = await session.get(DocumentRevision, document.current_revision_id)
    if revision is None:  # pragma: no cover - FK integrity guards this in practice
        raise DocumentNotComposableError("current revision not found")

    # Check blocking issues before the status check: a revision stuck at
    # REVIEW_REQUIRED (compose() never advances past that while blocking
    # issues are open) and a READY_FOR_APPROVAL revision undercut by a
    # brand new issue since composed are both really the same "unresolved
    # HIGH/CRITICAL issue" block from the caller's point of view, and
    # ApprovalBlockedError's structured blocking_issue_ids is strictly more
    # actionable than a generic "wrong status" message.
    blocking = await _open_blocking_issues(session, conversation_id=conversation_id)
    if blocking:
        raise ApprovalBlockedError([str(i.id) for i in blocking])

    if revision.status != DocumentRevisionStatus.READY_FOR_APPROVAL.value:
        raise DocumentNotComposableError(
            f"current revision is {revision.status!r}, not ready_for_approval"
        )

    validated_status = transition(
        DocumentRevisionStatus(revision.status), DocumentRevisionStatus.APPROVED
    )
    revision.status = validated_status.value
    revision.approved_by_user_id = approved_by.id
    revision.approved_at = datetime.now(UTC)
    await session.flush()

    document.status = validated_status.value
    await session.flush()

    await record_event(
        session,
        event_type="document.approved",
        user_id=approved_by.id,
        event_metadata={
            "conversation_id": str(conversation_id),
            "document_id": str(document.id),
            "revision_id": str(revision.id),
            "revision_number": revision.revision_number,
        },
    )
    return document
