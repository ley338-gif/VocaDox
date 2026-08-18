"""SQLAlchemy ORM models for the organizations domain.

Per the product spec, this is explicitly NOT SaaS multi-tenancy — it is
organizational/departmental separation within a single on-premise
installation (e.g. "General Medicine", "Psychotherapy", "Administration"
as sub-groups of one deployment). Phase 1 only implements the foundation
(tables + basic membership); org-scoped filtering of domain data (spec:
"filtered at the query layer, not just hidden in the UI") lands alongside
the domains that own that data in later phases.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.session import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_org_membership"),
    )
