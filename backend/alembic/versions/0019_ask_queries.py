"""ask_queries (post-GA P1-1: Ask VocaDox with enforced citation)

Adds the audit/history table for one asked question and its (possibly
empty) answer -- see `app.ask.models.AskQuery`'s docstring. No existing
column is dropped or renamed; no existing row's meaning changes.

Revision ID: 0019_ask_queries
Revises: 0018_vocabulary_entries
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_ask_queries"
down_revision: str | None = "0018_vocabulary_entries"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ask_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("asked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_statements", sa.JSON(), nullable=False),
        sa.Column("had_candidate_evidence", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ask_queries_organization_id", "ask_queries", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_ask_queries_organization_id", table_name="ask_queries")
    op.drop_table("ask_queries")
