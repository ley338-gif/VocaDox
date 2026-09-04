"""REST endpoints for the integrations domain (Phase 10, spec §54/§55):

- `/admin/service-accounts`, `/admin/webhooks` (+ `/admin/webhooks/{id}/
  deliveries`): human-session-authenticated admin CRUD, following the
  exact `require_permission(...)` + Phase 7 admin-viewer pattern every
  other `/admin/*` router in this codebase uses.
- `/integrations/api/...`: the scope-gated REST Integration API surface
  service accounts actually call. These routes are thin wrappers that
  call the *same* domain service functions the human-facing routers in
  `app.conversations.router`/`app.transcription.router`/
  `app.documents.router`/`app.templates.router` already call — no
  parallel business logic. They exist as a separate, additive route
  surface (rather than adding a second auth path to every existing human
  route) as a deliberate, documented scope decision for this phase — see
  PHASE_10_VALIDATION_REPORT.md, "Architecture Deviations".
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.models import Conversation, ConversationType, PrivacyMode
from app.conversations.schemas import ConversationCreateRequest, ConversationResponse
from app.conversations.service import create_conversation, list_conversations
from app.documents.api_schemas import ComposeRequest, DocumentResponse, DocumentRevisionResponse
from app.documents.models import Document, DocumentRevision
from app.documents.service import (
    ApprovalBlockedError,
    DocumentNotComposableError,
    approve_document,
    compose_document,
)
from app.identity.deps import require_csrf, require_permission
from app.identity.models import User
from app.integrations.deps import require_scope
from app.integrations.models import ServiceAccount, Webhook
from app.integrations.schemas import (
    AvailableScopesResponse,
    ServiceAccountCreatedResponse,
    ServiceAccountCreateRequest,
    ServiceAccountResponse,
    WebhookCreatedResponse,
    WebhookCreateRequest,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookEventTypesResponse,
    WebhookResponse,
    WebhookUpdateRequest,
)
from app.integrations.security import UnsafeWebhookURLError
from app.integrations.service import (
    WEBHOOK_EVENT_TYPES,
    create_service_account,
    create_webhook,
    list_deliveries,
    list_service_accounts,
    list_webhooks,
    revoke_service_account,
    rotate_service_account_secret,
    rotate_webhook_secret,
    update_webhook,
)
from app.platform.db.session import get_session
from app.templates.api_schemas import TemplateResponse
from app.templates.service import list_templates
from app.transcription.models import Transcript
from app.transcription.schemas import TranscriptResponse

admin_router = APIRouter(prefix="/admin", tags=["integrations-admin"])
api_router = APIRouter(prefix="/integrations/api", tags=["integrations-api"])

_require_sa_read = require_permission("service-account:read")
_require_sa_write = require_permission("service-account:write")
_require_webhook_read = require_permission("webhook:read")
_require_webhook_write = require_permission("webhook:write")

# The permission-code vocabulary a scope may be drawn from -- literally
# Phase 1's RBAC `permissions.code` values that map onto this phase's
# illustrative spec list (adapted to the real codes that exist -- e.g.
# `document:edit`, not the spec's `document:create`, is the real
# compose-a-document permission in this codebase).
AVAILABLE_SCOPES: tuple[str, ...] = (
    "conversation:read",
    "conversation:create",
    "transcript:read",
    "document:read",
    "document:edit",
    "document:approve",
    "template:read",
)

# Module-level singletons (ruff B008: a Depends(...) default must not call
# the factory inline) -- one per scope this phase's Integration API grants.
_require_conversation_read = require_scope("conversation:read")
_require_conversation_create = require_scope("conversation:create")
_require_transcript_read = require_scope("transcript:read")
_require_document_read = require_scope("document:read")
_require_document_edit = require_scope("document:edit")
_require_document_approve = require_scope("document:approve")
_require_template_read = require_scope("template:read")


# -- Admin: Service Accounts --------------------------------------------


@admin_router.get(
    "/service-accounts",
    response_model=list[ServiceAccountResponse],
    dependencies=[Depends(_require_sa_read)],
)
async def list_service_accounts_endpoint(
    organization_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[ServiceAccountResponse]:
    accounts = await list_service_accounts(db, organization_id=organization_id)
    return [ServiceAccountResponse.model_validate(a) for a in accounts]


@admin_router.post(
    "/service-accounts",
    response_model=ServiceAccountCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_account_endpoint(
    payload: ServiceAccountCreateRequest,
    user: User = Depends(_require_sa_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ServiceAccountCreatedResponse:
    unknown = set(payload.scopes) - set(AVAILABLE_SCOPES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown scope(s): {sorted(unknown)}",
        )
    account, api_key = await create_service_account(
        db,
        organization_id=payload.organization_id,
        name=payload.name,
        description=payload.description,
        scopes=payload.scopes,
        owner_user_id=payload.owner_user_id,
        created_by_user_id=user.id,
    )
    await record_event(
        db,
        event_type="service_account.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"service_account_id": str(account.id), "scopes": account.scopes},
    )
    await db.commit()
    await db.refresh(account)
    resp = ServiceAccountCreatedResponse(
        **ServiceAccountResponse.model_validate(account).model_dump(), api_key=api_key
    )
    return resp


@admin_router.post(
    "/service-accounts/{account_id}/rotate",
    response_model=ServiceAccountCreatedResponse,
)
async def rotate_service_account_endpoint(
    account_id: uuid.UUID,
    user: User = Depends(_require_sa_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ServiceAccountCreatedResponse:
    account = await db.get(ServiceAccount, account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="service account not found"
        )
    api_key = await rotate_service_account_secret(db, account)
    await record_event(
        db,
        event_type="service_account.rotated",
        user_id=user.id,
        username=user.username,
        event_metadata={"service_account_id": str(account.id)},
    )
    await db.commit()
    await db.refresh(account)
    resp = ServiceAccountCreatedResponse(
        **ServiceAccountResponse.model_validate(account).model_dump(), api_key=api_key
    )
    return resp


@admin_router.post(
    "/service-accounts/{account_id}/revoke",
    response_model=ServiceAccountResponse,
)
async def revoke_service_account_endpoint(
    account_id: uuid.UUID,
    user: User = Depends(_require_sa_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ServiceAccountResponse:
    account = await db.get(ServiceAccount, account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="service account not found"
        )
    await revoke_service_account(db, account)
    await record_event(
        db,
        event_type="service_account.revoked",
        user_id=user.id,
        username=user.username,
        event_metadata={"service_account_id": str(account.id)},
    )
    await db.commit()
    await db.refresh(account)
    return ServiceAccountResponse.model_validate(account)


@admin_router.get(
    "/service-accounts/scopes",
    response_model=AvailableScopesResponse,
    dependencies=[Depends(_require_sa_read)],
)
async def available_scopes_endpoint() -> AvailableScopesResponse:
    return AvailableScopesResponse(scopes=list(AVAILABLE_SCOPES))


# -- Admin: Webhooks ------------------------------------------------------


@admin_router.get(
    "/webhooks", response_model=list[WebhookResponse], dependencies=[Depends(_require_webhook_read)]
)
async def list_webhooks_endpoint(
    organization_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[WebhookResponse]:
    webhooks = await list_webhooks(db, organization_id=organization_id)
    return [WebhookResponse.model_validate(w) for w in webhooks]


@admin_router.get(
    "/webhooks/event-types",
    response_model=WebhookEventTypesResponse,
    dependencies=[Depends(_require_webhook_read)],
)
async def webhook_event_types_endpoint() -> WebhookEventTypesResponse:
    return WebhookEventTypesResponse(event_types=sorted(WEBHOOK_EVENT_TYPES))


@admin_router.post(
    "/webhooks", response_model=WebhookCreatedResponse, status_code=status.HTTP_201_CREATED
)
async def create_webhook_endpoint(
    payload: WebhookCreateRequest,
    user: User = Depends(_require_webhook_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> WebhookCreatedResponse:
    try:
        webhook, secret = await create_webhook(
            db,
            organization_id=payload.organization_id,
            name=payload.name,
            target_url=payload.target_url,
            event_types=payload.event_types,
            created_by_user_id=user.id,
        )
    except UnsafeWebhookURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await record_event(
        db,
        event_type="webhook.created",
        user_id=user.id,
        username=user.username,
        event_metadata={"webhook_id": str(webhook.id), "event_types": webhook.event_types},
    )
    await db.commit()
    await db.refresh(webhook)
    resp = WebhookCreatedResponse(
        **WebhookResponse.model_validate(webhook).model_dump(), secret=secret
    )
    return resp


@admin_router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook_endpoint(
    webhook_id: uuid.UUID,
    payload: WebhookUpdateRequest,
    user: User = Depends(_require_webhook_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> WebhookResponse:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    try:
        webhook = await update_webhook(
            db,
            webhook,
            name=payload.name,
            target_url=payload.target_url,
            event_types=payload.event_types,
            is_active=payload.is_active,
        )
    except UnsafeWebhookURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await record_event(
        db,
        event_type="webhook.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"webhook_id": str(webhook.id)},
    )
    await db.commit()
    await db.refresh(webhook)
    return WebhookResponse.model_validate(webhook)


@admin_router.post("/webhooks/{webhook_id}/rotate-secret", response_model=WebhookCreatedResponse)
async def rotate_webhook_secret_endpoint(
    webhook_id: uuid.UUID,
    user: User = Depends(_require_webhook_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> WebhookCreatedResponse:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    secret = await rotate_webhook_secret(db, webhook)
    await record_event(
        db,
        event_type="webhook.updated",
        user_id=user.id,
        username=user.username,
        event_metadata={"webhook_id": str(webhook.id), "action": "secret_rotated"},
    )
    await db.commit()
    await db.refresh(webhook)
    resp = WebhookCreatedResponse(
        **WebhookResponse.model_validate(webhook).model_dump(), secret=secret
    )
    return resp


@admin_router.delete(
    "/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_webhook_endpoint(
    webhook_id: uuid.UUID,
    user: User = Depends(_require_webhook_write),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    await db.delete(webhook)
    await record_event(
        db,
        event_type="webhook.deleted",
        user_id=user.id,
        username=user.username,
        event_metadata={"webhook_id": str(webhook_id)},
    )
    await db.commit()


@admin_router.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
    dependencies=[Depends(_require_webhook_read)],
)
async def list_webhook_deliveries_endpoint(
    webhook_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> WebhookDeliveryListResponse:
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    deliveries, total = await list_deliveries(db, webhook_id=webhook_id, limit=limit, offset=offset)
    return WebhookDeliveryListResponse(
        items=[WebhookDeliveryResponse.model_validate(d) for d in deliveries], total=total
    )


# -- Integration API: scope-gated, service-account-authenticated --------


def _require_owner(account: ServiceAccount) -> uuid.UUID:
    if account.owner_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="service account has no owner_user_id configured for write attribution",
        )
    return account.owner_user_id


@api_router.get("/conversations", response_model=list[ConversationResponse])
async def api_list_conversations(
    account: ServiceAccount = Depends(_require_conversation_read),
    db: AsyncSession = Depends(get_session),
) -> list[ConversationResponse]:
    conversations, _total = await list_conversations(db, organization_ids={account.organization_id})
    return [ConversationResponse.model_validate(c) for c in conversations]


@api_router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def api_get_conversation(
    conversation_id: uuid.UUID,
    account: ServiceAccount = Depends(_require_conversation_read),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    conversation = await _get_scoped_conversation(db, account, conversation_id)
    return ConversationResponse.model_validate(conversation)


@api_router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
async def api_create_conversation(
    payload: ConversationCreateRequest,
    account: ServiceAccount = Depends(_require_conversation_create),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    owner_user_id = _require_owner(account)
    conversation = await create_conversation(
        db,
        organization_id=account.organization_id,
        created_by_user_id=owner_user_id,
        title=payload.title,
        description=payload.description,
        conversation_type=ConversationType(payload.conversation_type),
        external_reference=payload.external_reference,
        external_reference_type=payload.external_reference_type,
        privacy_mode=PrivacyMode(payload.privacy_mode),
        processing_profile_id=payload.processing_profile_id,
    )
    await record_event(
        db,
        event_type="conversation.created",
        user_id=owner_user_id,
        event_metadata={"conversation_id": str(conversation.id), "via": "service_account"},
    )
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@api_router.get("/conversations/{conversation_id}/transcript", response_model=TranscriptResponse)
async def api_get_transcript(
    conversation_id: uuid.UUID,
    account: ServiceAccount = Depends(_require_transcript_read),
    db: AsyncSession = Depends(get_session),
) -> TranscriptResponse:
    await _get_scoped_conversation(db, account, conversation_id)
    result = await db.execute(
        select(Transcript).where(
            Transcript.conversation_id == conversation_id, Transcript.is_active.is_(True)
        )
    )
    transcript = result.scalars().first()
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transcript not found")
    return TranscriptResponse.model_validate(transcript)


@api_router.get("/conversations/{conversation_id}/document", response_model=DocumentResponse)
async def api_get_document(
    conversation_id: uuid.UUID,
    account: ServiceAccount = Depends(_require_document_read),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    await _get_scoped_conversation(db, account, conversation_id)
    result = await db.execute(select(Document).where(Document.conversation_id == conversation_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no document composed yet"
        )
    revision = (
        await db.get(DocumentRevision, document.current_revision_id)
        if document.current_revision_id
        else None
    )
    resp = DocumentResponse.model_validate(document)
    resp.current_revision = (
        DocumentRevisionResponse.model_validate(revision) if revision is not None else None
    )
    return resp


@api_router.post(
    "/conversations/{conversation_id}/document/compose", response_model=DocumentResponse
)
async def api_compose_document(
    conversation_id: uuid.UUID,
    body: ComposeRequest,  # noqa: ARG001 - reserved, always empty today (matches the human route)
    account: ServiceAccount = Depends(_require_document_edit),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    await _get_scoped_conversation(db, account, conversation_id)
    owner_user_id = _require_owner(account)
    owner = await db.get(User, owner_user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="owner_user_id not found")
    try:
        document = await compose_document(db, conversation_id=conversation_id, requested_by=owner)
    except DocumentNotComposableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(document)
    revision = (
        await db.get(DocumentRevision, document.current_revision_id)
        if document.current_revision_id
        else None
    )
    resp = DocumentResponse.model_validate(document)
    resp.current_revision = (
        DocumentRevisionResponse.model_validate(revision) if revision is not None else None
    )
    return resp


@api_router.post(
    "/conversations/{conversation_id}/document/approve", response_model=DocumentResponse
)
async def api_approve_document(
    conversation_id: uuid.UUID,
    account: ServiceAccount = Depends(_require_document_approve),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    await _get_scoped_conversation(db, account, conversation_id)
    owner_user_id = _require_owner(account)
    owner = await db.get(User, owner_user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="owner_user_id not found")
    result = await db.execute(select(Document).where(Document.conversation_id == conversation_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no document composed yet"
        )
    try:
        document = await approve_document(
            db, document=document, conversation_id=conversation_id, approved_by=owner
        )
    except ApprovalBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "blocked by open review issues", "blocking_issue_ids": exc.args[0]},
        ) from exc
    except DocumentNotComposableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(document)
    revision = (
        await db.get(DocumentRevision, document.current_revision_id)
        if document.current_revision_id
        else None
    )
    resp = DocumentResponse.model_validate(document)
    resp.current_revision = (
        DocumentRevisionResponse.model_validate(revision) if revision is not None else None
    )
    return resp


@api_router.get("/templates", response_model=list[TemplateResponse])
async def api_list_templates(
    account: ServiceAccount = Depends(_require_template_read),  # noqa: ARG001
    db: AsyncSession = Depends(get_session),
) -> list[TemplateResponse]:
    templates = await list_templates(db)
    return [TemplateResponse.model_validate(t) for t in templates]


async def _get_scoped_conversation(
    db: AsyncSession, account: ServiceAccount, conversation_id: uuid.UUID
) -> Conversation:
    """Same "404 for doesn't-exist AND wrong-org alike" posture as
    `app.conversations.authz.authorize_conversation_access` — a service
    account must never learn that a conversation exists in an
    organization it isn't scoped to."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.deleted_at.is_(None)
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None or conversation.organization_id != account.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return conversation
