"""conversation_participants.user_id (post-GA: participants pulled from
the registered-user directory)

Adds a second, independent optional link on `ConversationParticipant` —
alongside the existing `known_speaker_id` (org-wide *external* identity
bookkeeping) — to a registered `users` row: the system user who was
actually present, enabling later "I was there" attribution / avatar
display while keeping `display_name` as the always-present, never-
required-to-be-a-real-name label (both links may be set at once, or
neither).

`ondelete="SET NULL"` mirrors `known_speaker_id`'s existing FK: deleting a
user must not alter an existing (possibly already-shared) conversation's
participant row -- only the link is cleared, `display_name` remains as the
historical value.

Revision ID: 0029_participant_user_link
Revises: 0028_hash_recap_share_tokens
Create Date: 2026-09-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_participant_user_link"
down_revision: str | None = "0028_hash_recap_share_tokens"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_participants",
        sa.Column("user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversation_participants_user_id",
        "conversation_participants",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversation_participants_user_id",
        "conversation_participants",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_participants_user_id",
        table_name="conversation_participants",
    )
    op.drop_constraint(
        "fk_conversation_participants_user_id",
        "conversation_participants",
        type_="foreignkey",
    )
    op.drop_column("conversation_participants", "user_id")
