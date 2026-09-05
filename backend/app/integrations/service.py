"""Integrations domain service: Service Account CRUD/rotation/revocation/
authentication, Webhook CRUD/secret-rotation, and event dispatch with HMAC
signing, bounded retry+backoff, and delivery logging (Phase 10, spec §54/
§55, roadmap §73).

Dispatch is hooked onto `app.audit.service.record_event` (see
`maybe_dispatch_webhooks`, called from there) rather than re-detecting
conversation/document/processing state transitions here — every event
type this phase can subscribe to already has a real, existing
`record_event(event_type=...)` call site from Phases 1-9; this module
adds no parallel event-detection logic, only routes the audit event to
matching webhooks and no-ops for organizations/event types with none.

Delivery is fire-and-forget (`asyncio.create_task`, its own DB session,
not the request's) so a slow/unreachable webhook target never blocks the
HTTP response that triggered it. This is a deliberate, documented
trade-off (see PHASE_10_VALIDATION_REPORT.md "Known Limitations"): a
process restart mid-retry loses the in-flight retry schedule (the delivery
attempts already made are still durably logged in `webhook_deliveries`,
only the *pending* retry is lost) — moving this to the existing
Valkey-backed job queue (`app.processing.queues`) for durable retries is
flagged as a follow-up, not required for this phase's merge gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conversations.models import Conversation
from app.identity.passwords import hash_password, verify_password
from app.integrations.models import ServiceAccount, Webhook, WebhookDelivery, WebhookDeliveryStatus
from app.integrations.security import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    generate_service_account_key,
    generate_webhook_secret,
    parse_api_key,
    sign_payload,
    validate_webhook_url,
)
from app.platform.db.session import get_sessionmaker
from app.processing.models import ProcessingRun

logger = logging.getLogger("vocadox.integrations")

# Test seam: `dispatch_with_retry` normally uses the process-wide real
# engine's sessionmaker (`get_sessionmaker()`), since it runs from a
# detached `asyncio.create_task` with no request-scoped session to reuse
# (see `maybe_dispatch_webhooks`). Tests run against an in-memory SQLite
# engine reachable only through the FastAPI `get_session` dependency
# override, which a background task never goes through -- so
# `tests/integrations/conftest.py` points this override at the test
# engine's sessionmaker for the duration of each test. Production code
# never calls `set_dispatch_sessionmaker`.
_dispatch_sessionmaker_override: async_sessionmaker[AsyncSession] | None = None


def set_dispatch_sessionmaker(sessionmaker: async_sessionmaker[AsyncSession] | None) -> None:
    global _dispatch_sessionmaker_override
    _dispatch_sessionmaker_override = sessionmaker


def _get_dispatch_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return _dispatch_sessionmaker_override or get_sessionmaker()

# The audit event types (exact strings already emitted across Phases 1-9 —
# see docs referenced in each router/service module) that a webhook may
# subscribe to. `review.required` was added in this phase alongside the
# webhook feature itself (see app.intelligence.service.run_extraction) --
# every other value already existed before Phase 10.
WEBHOOK_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "conversation.created",
        "conversation.deleted",
        "processing.started",
        "processing.completed",
        "processing.failed",
        "review.required",
        "document.created",
        "document.approved",
        # Phase 11 (spec §64/§56/§57): operations events — an admin can
        # wire an external alerting system to a real backup/retention-
        # cleanup run without polling the admin UI.
        "backup.created",
        "retention_cleanup.run",
        "retention_cleanup.item_deleted",
    }
)

# Metadata keys ever forwarded into a webhook payload. Defense in depth on
# top of "audit events never contain content" — even if a future
# record_event() call site accidentally puts something richer in
# event_metadata, only these known-safe id/count/status fields leave the
# system by default. Spec: "Keine Gesprächsinhalte standardmäßig im
# Payload."
_SAFE_PAYLOAD_KEYS = frozenset(
    {
        "conversation_id",
        "document_id",
        "revision_id",
        "revision_number",
        "processing_run_id",
        "transcript_id",
        "source_media_id",
        "review_issues_created",
        "status",
        "fact_count",
        "run_type",
        "reprocess",
        # Phase 11
        "backup_id",
        "database_dump_bytes",
        "media_archive_bytes",
        "run_id",
        "dry_run",
        "conversations_evaluated",
        "items_deleted",
        "bytes_freed",
        "action",
        "reason",
    }
)

DEFAULT_BACKOFF_SCHEDULE: tuple[float, ...] = (2.0, 10.0, 60.0, 300.0)
DELIVERY_TIMEOUT_SECONDS = 10.0

# (url, body, headers) -> (status_code, response_text) -- the seam
# `attempt_delivery`'s `http_post` param and `_default_http_post` share, so
# tests can inject a fake transport without a real network call.
HttpPost = Callable[[str, bytes, dict[str, str]], Awaitable[tuple[int, str]]]


# -- Service Accounts -----------------------------------------------------


async def create_service_account(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    description: str | None,
    scopes: list[str],
    owner_user_id: uuid.UUID | None,
    created_by_user_id: uuid.UUID | None,
) -> tuple[ServiceAccount, str]:
    key_prefix, secret, api_key = generate_service_account_key()
    account = ServiceAccount(
        organization_id=organization_id,
        name=name,
        description=description,
        key_prefix=key_prefix,
        secret_hash=hash_password(secret),
        scopes=scopes,
        owner_user_id=owner_user_id,
        created_by_user_id=created_by_user_id,
    )
    session.add(account)
    await session.flush()
    return account, api_key


async def rotate_service_account_secret(session: AsyncSession, account: ServiceAccount) -> str:
    """Issues a new key_prefix + secret and immediately invalidates the
    old one (old secret_hash is overwritten, so the previous API key stops
    authenticating the instant this commits)."""
    key_prefix, secret, api_key = generate_service_account_key()
    account.key_prefix = key_prefix
    account.secret_hash = hash_password(secret)
    account.last_rotated_at = datetime.now(UTC)
    await session.flush()
    return api_key


async def revoke_service_account(session: AsyncSession, account: ServiceAccount) -> None:
    account.is_active = False
    await session.flush()


async def authenticate_service_account(
    session: AsyncSession, api_key: str
) -> ServiceAccount | None:
    parsed = parse_api_key(api_key)
    if parsed is None:
        return None
    key_prefix, secret = parsed
    result = await session.execute(
        select(ServiceAccount).where(ServiceAccount.key_prefix == key_prefix)
    )
    account = result.scalar_one_or_none()
    if account is None or not account.is_active:
        return None
    if not verify_password(secret, account.secret_hash):
        return None
    account.last_used_at = datetime.now(UTC)
    await session.flush()
    return account


async def list_service_accounts(
    session: AsyncSession, *, organization_id: uuid.UUID | None = None
) -> list[ServiceAccount]:
    stmt = select(ServiceAccount).order_by(ServiceAccount.created_at.desc())
    if organization_id is not None:
        stmt = stmt.where(ServiceAccount.organization_id == organization_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# -- Webhooks ---------------------------------------------------------------


async def create_webhook(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    target_url: str,
    event_types: list[str],
    created_by_user_id: uuid.UUID | None,
) -> tuple[Webhook, str]:
    validate_webhook_url(target_url)
    _validate_event_types(event_types)
    secret = generate_webhook_secret()
    webhook = Webhook(
        organization_id=organization_id,
        name=name,
        target_url=target_url,
        secret=secret,
        event_types=event_types,
        created_by_user_id=created_by_user_id,
    )
    session.add(webhook)
    await session.flush()
    return webhook, secret


def _validate_event_types(event_types: list[str]) -> None:
    unknown = set(event_types) - WEBHOOK_EVENT_TYPES
    if unknown:
        raise ValueError(f"unknown webhook event type(s): {sorted(unknown)}")


async def update_webhook(
    session: AsyncSession,
    webhook: Webhook,
    *,
    name: str | None = None,
    target_url: str | None = None,
    event_types: list[str] | None = None,
    is_active: bool | None = None,
) -> Webhook:
    if target_url is not None:
        validate_webhook_url(target_url)
        webhook.target_url = target_url
    if event_types is not None:
        _validate_event_types(event_types)
        webhook.event_types = event_types
    if name is not None:
        webhook.name = name
    if is_active is not None:
        webhook.is_active = is_active
    await session.flush()
    return webhook


async def rotate_webhook_secret(session: AsyncSession, webhook: Webhook) -> str:
    secret = generate_webhook_secret()
    webhook.secret = secret
    await session.flush()
    return secret


async def list_webhooks(
    session: AsyncSession, *, organization_id: uuid.UUID | None = None
) -> list[Webhook]:
    stmt = select(Webhook).order_by(Webhook.created_at.desc())
    if organization_id is not None:
        stmt = stmt.where(Webhook.organization_id == organization_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_deliveries(
    session: AsyncSession, *, webhook_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[WebhookDelivery], int]:
    count_stmt = select(func.count()).select_from(WebhookDelivery).where(
        WebhookDelivery.webhook_id == webhook_id
    )
    total = int((await session.execute(count_stmt)).scalar_one())
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


# -- Event payload + dispatch ------------------------------------------------


def build_event_payload(
    event_type: str, event_metadata: dict[str, object] | None, audit_event_id: uuid.UUID
) -> dict[str, object]:
    safe_metadata = {
        k: v for k, v in (event_metadata or {}).items() if k in _SAFE_PAYLOAD_KEYS
    }
    return {
        "event_type": event_type,
        "event_id": str(audit_event_id),
        "occurred_at": datetime.now(UTC).isoformat(),
        **safe_metadata,
    }


async def _resolve_organization_id(
    session: AsyncSession, event_metadata: dict[str, object] | None
) -> uuid.UUID | None:
    if not event_metadata:
        return None
    org_raw = event_metadata.get("organization_id")
    if org_raw:
        return org_raw if isinstance(org_raw, uuid.UUID) else uuid.UUID(str(org_raw))

    conv_raw = event_metadata.get("conversation_id")
    if conv_raw:
        conversation = await session.get(Conversation, uuid.UUID(str(conv_raw)))
        return conversation.organization_id if conversation else None

    run_raw = event_metadata.get("processing_run_id")
    if run_raw:
        run = await session.get(ProcessingRun, uuid.UUID(str(run_raw)))
        if run is not None:
            conversation = await session.get(Conversation, run.conversation_id)
            return conversation.organization_id if conversation else None

    return None


async def maybe_dispatch_webhooks(
    session: AsyncSession,
    *,
    event_type: str,
    event_metadata: dict[str, object] | None,
    audit_event_id: uuid.UUID,
) -> None:
    """Called by `app.audit.service.record_event` right after it persists
    an AuditEvent. No-ops immediately (no extra query) for any event type
    this phase doesn't support webhooks for."""
    if event_type not in WEBHOOK_EVENT_TYPES:
        return
    organization_id = await _resolve_organization_id(session, event_metadata)
    if organization_id is None:
        return

    result = await session.execute(
        select(Webhook).where(
            Webhook.organization_id == organization_id, Webhook.is_active.is_(True)
        )
    )
    matching = [w for w in result.scalars().all() if event_type in (w.event_types or [])]
    if not matching:
        return

    payload = build_event_payload(event_type, event_metadata, audit_event_id)
    for webhook in matching:
        # Fire-and-forget: uses its own session (see module docstring),
        # deliberately not awaited so a slow/hanging endpoint never blocks
        # the request that produced the triggering event.
        task = asyncio.create_task(dispatch_with_retry(webhook.id, event_type, payload))
        task.add_done_callback(_log_task_exception)


def _log_task_exception(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("webhook dispatch task failed", exc_info=exc)


async def attempt_delivery(
    session: AsyncSession,
    webhook: Webhook,
    *,
    event_type: str,
    payload: dict[str, object],
    attempt_number: int,
    http_post: HttpPost | None = None,
) -> WebhookDelivery:
    """Makes exactly one real HTTP delivery attempt and persists the
    result as a WebhookDelivery row (committed here, not left to the
    caller, so a delivery is always durably logged even if the retry loop
    around it later fails for an unrelated reason)."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    delivery_id = uuid.uuid4()
    signature = sign_payload(webhook.secret, body)
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature,
        EVENT_HEADER: event_type,
        DELIVERY_HEADER: str(delivery_id),
    }

    status_value = WebhookDeliveryStatus.FAILED
    response_status_code: int | None = None
    error_message: str | None = None

    poster = http_post or _default_http_post
    try:
        response_status_code, response_text = await poster(webhook.target_url, body, headers)
        if 200 <= response_status_code < 300:
            status_value = WebhookDeliveryStatus.SUCCESS
        else:
            error_message = f"non-2xx response: {response_status_code} {response_text[:200]}"
    except Exception as exc:  # noqa: BLE001 - any transport failure is a delivery failure
        error_message = f"{type(exc).__name__}: {exc}"

    delivery = WebhookDelivery(
        id=delivery_id,
        webhook_id=webhook.id,
        event_type=event_type,
        payload=payload,
        attempt_number=attempt_number,
        status=status_value.value,
        response_status_code=response_status_code,
        error_message=error_message,
        delivered_at=datetime.now(UTC) if status_value == WebhookDeliveryStatus.SUCCESS else None,
    )
    session.add(delivery)
    await session.commit()
    return delivery


async def _default_http_post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    import httpx

    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
        response = await client.post(url, content=body, headers=headers)
        return response.status_code, response.text


async def dispatch_with_retry(
    webhook_id: uuid.UUID,
    event_type: str,
    payload: dict[str, object],
    *,
    backoff_schedule: tuple[float, ...] = DEFAULT_BACKOFF_SCHEDULE,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    http_post: HttpPost | None = None,
) -> None:
    """Bounded retry loop: 1 initial attempt + len(backoff_schedule)
    retries (5 attempts total with the default schedule), never infinite.
    Each attempt is durably logged via `attempt_delivery` regardless of
    outcome."""
    max_attempts = len(backoff_schedule) + 1
    sessionmaker = _get_dispatch_sessionmaker()

    for attempt in range(1, max_attempts + 1):
        async with sessionmaker() as session:
            webhook = await session.get(Webhook, webhook_id)
            if webhook is None or not webhook.is_active:
                return
            delivery = await attempt_delivery(
                session,
                webhook,
                event_type=event_type,
                payload=payload,
                attempt_number=attempt,
                http_post=http_post,
            )

        if delivery.status == WebhookDeliveryStatus.SUCCESS.value:
            return

        is_last_attempt = attempt == max_attempts
        if is_last_attempt:
            async with sessionmaker() as session:
                exhausted = await session.get(WebhookDelivery, delivery.id)
                if exhausted is not None:
                    exhausted.status = WebhookDeliveryStatus.EXHAUSTED.value
                    await session.commit()
            return

        await sleep(backoff_schedule[attempt - 1])
