"""Store public recap bearer tokens only as SHA-256 digests.

Revision ID: 0028_hash_recap_share_tokens
Revises: 0027_session_generation
Create Date: 2026-09-10
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_hash_recap_share_tokens"
down_revision: str | None = "0027_session_generation"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recap_share_links", sa.Column("token_hash", sa.String(64), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, token FROM recap_share_links"))
    for row in rows:
        digest = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text("UPDATE recap_share_links SET token_hash = :digest WHERE id = :id"),
            {"digest": digest, "id": row.id},
        )
    op.alter_column("recap_share_links", "token_hash", nullable=False)
    op.create_index(
        "ix_recap_share_links_token_hash", "recap_share_links", ["token_hash"], unique=True
    )
    op.drop_index("ix_recap_share_links_token", table_name="recap_share_links")
    op.drop_constraint("recap_share_links_token_key", "recap_share_links", type_="unique")
    op.drop_column("recap_share_links", "token")


def downgrade() -> None:
    op.add_column("recap_share_links", sa.Column("token", sa.String(64), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE recap_share_links SET token = token_hash"))
    op.alter_column("recap_share_links", "token", nullable=False)
    op.create_unique_constraint("recap_share_links_token_key", "recap_share_links", ["token"])
    op.create_index("ix_recap_share_links_token", "recap_share_links", ["token"], unique=True)
    op.drop_index("ix_recap_share_links_token_hash", table_name="recap_share_links")
    op.drop_column("recap_share_links", "token_hash")
