"""follow_up_tasks (Phase 9: Longitudinal Documentation)

Phase 9 (spec §39/§40/§41, roadmap §73) adds exactly one new table:

- `follow_up_tasks`: a generic Follow-up/Task entity. `source` is either
  `ai_extracted` (linked back to the originating `extracted_facts` row via
  `source_fact_id`, Phase 4's existing `task` extraction category) or
  `user_created` (a human adds it directly, `source_fact_id` is NULL).
  `organization_id` is denormalized onto every row (also reachable via
  `conversation_id`) so the cross-organization isolation queries this
  phase depends on never need a join to be correct.

Timeline/external-reference grouping and Comparison are built entirely as
READ queries over Phase 2's existing `conversations.external_reference`
and Phase 4's existing `extracted_facts` -- no new column or table is
needed for either.

No existing column is dropped or renamed; this is a purely additive
migration. Every Phase 0-8 row/table is unaffected.

Revision ID: 0010_longitudinal_documentation
Revises: 0009_analytics_evaluation
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_longitudinal_documentation"
down_revision: str | None = "0009_analytics_evaluation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follow_up_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_fact_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=1024), nullable=False),
        sa.Column("assignee", sa.String(length=256), nullable=True),
        sa.Column("due_date", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_fact_id"], ["extracted_facts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_follow_up_tasks_organization_id", "follow_up_tasks", ["organization_id"]
    )
    op.create_index(
        "ix_follow_up_tasks_conversation_id", "follow_up_tasks", ["conversation_id"]
    )
    op.create_index("ix_follow_up_tasks_source", "follow_up_tasks", ["source"])
    op.create_index("ix_follow_up_tasks_status", "follow_up_tasks", ["status"])
    op.create_index("ix_follow_up_tasks_created_at", "follow_up_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_created_at", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_status", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_source", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_conversation_id", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_organization_id", table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")
