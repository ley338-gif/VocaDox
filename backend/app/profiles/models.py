"""Minimal `ModelProfile` foundation (spec §17/§18): just enough so the
extraction model is configuration (a DB row), never a hardcoded string in
worker code — NOT the full Phase 6 Processing Profiles system (Speech
Profile + Diarization Profile + Extraction Model + Document Model +
Template + Prompt Version + Language + Retention Policy combined into
named presets). That whole multi-profile admin UX is explicitly out of
scope for Phase 4 — see docs/architecture/future-considerations.md.

Exactly one enabled profile per `purpose` is expected to exist at a time
(enforced by app.profiles.seed's idempotent bootstrap, not a DB
constraint — a future admin UI, if ever built, would need one); the
extraction worker resolves its model via
`app.profiles.service.get_active_profile(purpose="extraction")` rather
than reading Settings directly, so switching models is a data change, not
a code change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.session import Base


class ModelProfilePurpose(StrEnum):
    EXTRACTION = "extraction"
    # DOCUMENT_GENERATION reserved for Phase 5 — not created/used here.


class ModelProfile(Base):
    __tablename__ = "model_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # "ollama" | "fake"
    model_identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
