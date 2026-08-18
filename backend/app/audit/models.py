"""SQLAlchemy ORM model for audit events.

General-purpose event log, first used for login/login_failed/logout in
Phase 1 but intentionally shaped to be reused by later domains (spec hard
rule, kept front-of-mind here even though no conversation data exists yet):
audit events must NEVER contain full conversation content, passwords,
tokens, or other secrets. `event_metadata` is for small, structured,
non-sensitive context only (e.g. {"reason": "invalid_password"}) — never a
dumping ground for request bodies.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Nullable + denormalized username: login_failed events may not resolve
    # to a real user_id (unknown username), and we still want the actor
    # label to survive if the user row is later deleted.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    event_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
