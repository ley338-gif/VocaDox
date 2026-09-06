"""conversations.group_id, follow_up_tasks.group_id (post-GA: team-scoped
conversation/task visibility)

Adds an optional "team" (reusing the existing `Group` model, which already
exists in the data model precisely for this purpose — its own docstring:
"the on-prem organizational/departmental grouping mechanism") to
`Conversation`. A conversation with `group_id IS NULL` stays visible to
every member of its organization exactly as today — nothing about
existing conversations changes; only conversations that get an explicit
team assigned going forward become scoped to that team's members (plus
`system:admin` and the new `conversation:read-cross-team` permission).

`follow_up_tasks.group_id` denormalizes the parent conversation's team at
creation time, mirroring this table's existing `organization_id`
denormalization (see app/longitudinal/models.py's own docstring: "so
cross-organization queries/isolation checks never need a join to be
correct") — the same reasoning applies to team-scoping the org-wide
Aufgaben list.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0015_conversation_team_scope
Revises: 0014_recaps
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_conversation_team_scope"
down_revision: str | None = "0014_recaps"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_group_id",
        "conversations",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_conversations_group_id", "conversations", ["group_id"])

    op.add_column("follow_up_tasks", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_follow_up_tasks_group_id",
        "follow_up_tasks",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_follow_up_tasks_group_id", "follow_up_tasks", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_group_id", table_name="follow_up_tasks")
    op.drop_constraint("fk_follow_up_tasks_group_id", "follow_up_tasks", type_="foreignkey")
    op.drop_column("follow_up_tasks", "group_id")

    op.drop_index("ix_conversations_group_id", table_name="conversations")
    op.drop_constraint("fk_conversations_group_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "group_id")
