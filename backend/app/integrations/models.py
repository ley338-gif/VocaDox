"""SQLAlchemy ORM models for the integrations domain (Phase 10, spec §54/
§55, roadmap §73).

Two machine-to-machine primitives:

- `ServiceAccount`: a non-human API client identity, always scoped to
  exactly one `Organization` (least-privilege: no "global" service account
  exists — an install that genuinely needs cross-org access creates one
  per organization, mirroring the org-scoped filtering every other domain
  already enforces). Authenticates via an API key
  (`{key_prefix}.{secret}`, Bearer-token style); `secret_hash` reuses
  Phase 1's Argon2id hasher (`app.identity.passwords`) — never a second
  hashing scheme. The raw secret is NEVER stored and NEVER retrievable
  after creation/rotation (show-once, like every real API-key UX).
  `scopes` is a JSON list of the *same* `permissions.code` strings Phase
  1's RBAC already defines — not a parallel authorization vocabulary.
  `owner_user_id` is an admin-designated real `User` a service account's
  writes are attributed to (mirrors "acting as" patterns in GitHub Apps/
  Stripe Connect) — required for any scope that performs a write.

- `Webhook`: an admin-configured HTTP delivery target for one
  `Organization`, subscribed to a set of event types (mapped 1:1 from the
  audit event types already emitted across Phases 1-9 — see
  `app.integrations.service.WEBHOOK_EVENT_TYPES`). `secret` is stored in
  recoverable (plaintext) form because, unlike a service-account secret,
  it must be re-read on every delivery to compute the outbound HMAC
  signature — this is standard for this pattern (Stripe/GitHub store
  their webhook signing secrets the same way) and is documented as a
  deliberate deviation from "always hash" in
  `PHASE_10_VALIDATION_REPORT.md`. It is still never logged, never
  returned in a read/list response (only in the create/rotate response
  body, once), and update/list endpoints must keep leaving it out.

- `WebhookDelivery`: one row per delivery *attempt* (not per event) —
  `attempt_number` increments on each retry, so this table is both the
  admin-visible Delivery Log (spec) and the retry bookkeeping.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class WebhookDeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"  # this attempt failed, more attempts remain
    EXHAUSTED = "exhausted"  # final attempt failed, retry budget spent


class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    key_prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Plaintext by necessity (re-read on every delivery to sign) — see the
    # module docstring. Never selected by list/read endpoints.
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # IDs/metadata only -- never conversation/transcript/fact/document
    # content, see app.integrations.service.build_event_payload.
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WebhookDeliveryStatus.PENDING.value
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
