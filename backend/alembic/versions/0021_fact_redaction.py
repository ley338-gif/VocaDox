"""fact_redaction (post-GA P3-2: fact-level redaction, evidence chain
preserved)

Adds `extracted_facts.is_redacted` (current-state cache) and the
`fact_redaction_events` audit table (one immutable row per redact/
un-redact action) -- see `app.intelligence.models.ExtractedFact.
is_redacted`'s docstring for why this is orthogonal to `review_status`
and never deletes anything.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0021_fact_redaction
Revises: 0020_voiceprints
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_fact_redaction"
down_revision: str | None = "0020_voiceprints"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extracted_facts",
        sa.Column("is_redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_extracted_facts_is_redacted", "extracted_facts", ["is_redacted"]
    )

    op.create_table(
        "fact_redaction_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("redacted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fact_id"], ["extracted_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fact_redaction_events_fact_id", "fact_redaction_events", ["fact_id"]
    )
    op.create_index(
        "ix_fact_redaction_events_created_at", "fact_redaction_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_fact_redaction_events_created_at", table_name="fact_redaction_events")
    op.drop_index("ix_fact_redaction_events_fact_id", table_name="fact_redaction_events")
    op.drop_table("fact_redaction_events")

    op.drop_index("ix_extracted_facts_is_redacted", table_name="extracted_facts")
    op.drop_column("extracted_facts", "is_redacted")
