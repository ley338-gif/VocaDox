"""processing outbox (transactional outbox pattern)

Phase 3.1 hardening: adds `processing_outbox`, closing the Phase 3
Postgres/Valkey dual-write race documented in
`docs/architecture/processing-jobs.md` and
`app.processing.models.OutboxStatus`. No existing table is altered.

Revision ID: 0005_processing_outbox
Revises: 0004_speech_diarization
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_processing_outbox"
down_revision: str | None = "0004_speech_diarization"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("queue_name", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_outbox_job_id", "processing_outbox", ["job_id"])
    op.create_index("ix_processing_outbox_status", "processing_outbox", ["status"])


def downgrade() -> None:
    op.drop_index("ix_processing_outbox_status", table_name="processing_outbox")
    op.drop_index("ix_processing_outbox_job_id", table_name="processing_outbox")
    op.drop_table("processing_outbox")
