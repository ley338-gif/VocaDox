"""recap_share_links (post-GA P3-2: expiring public share links for the
Recap)

Adds the `recap_share_links` table -- see `app.recap.models.
RecapShareLink`'s docstring. Tokens are opaque, cryptographically random
strings; the table carries no recap content itself, only enough to
validate a token and locate the conversation whose (always-live) current
recap revision to serve.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0022_recap_share_links
Revises: 0021_fact_redaction
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_recap_share_links"
down_revision: str | None = "0021_fact_redaction"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recap_share_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_recap_share_links_conversation_id", "recap_share_links", ["conversation_id"])
    op.create_index("ix_recap_share_links_token", "recap_share_links", ["token"], unique=True)
    op.create_index("ix_recap_share_links_created_at", "recap_share_links", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_recap_share_links_created_at", table_name="recap_share_links")
    op.drop_index("ix_recap_share_links_token", table_name="recap_share_links")
    op.drop_index("ix_recap_share_links_conversation_id", table_name="recap_share_links")
    op.drop_table("recap_share_links")
