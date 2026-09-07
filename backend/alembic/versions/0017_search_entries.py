"""search_entries (post-GA P0-1: full-text search index)

Adds the cross-conversation search index table: one denormalized row per
searchable unit (a transcript segment, an extracted fact, or a
conversation's current document), see `app.search.models.SearchEntry`'s
docstring for the design. `organization_id`/`group_id` are denormalized
from the owning conversation, mirroring `follow_up_tasks` (0009/0015).

The actual full-text column (`tsv`, a STORED generated `tsvector` over
`content`, German text-search configuration) and its GIN index are
raw DDL, not SQLAlchemy-mapped -- see
`docs/architecture/adr/0030-search-index-dual-dialect.md`: this column
only exists on real Postgres (alembic migrations in this project always
target real Postgres, never the SQLite test DB, so no dialect branch is
needed here).

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0017_search_entries
Revises: 0016_speaker_corrections
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_search_entries"
down_revision: str | None = "0016_speaker_corrections"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_search_entries_source"),
    )
    op.create_index("ix_search_entries_conversation_id", "search_entries", ["conversation_id"])
    op.create_index("ix_search_entries_organization_id", "search_entries", ["organization_id"])
    op.create_index("ix_search_entries_group_id", "search_entries", ["group_id"])
    op.create_index("ix_search_entries_source_type", "search_entries", ["source_type"])

    op.execute(
        "ALTER TABLE search_entries ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('german', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_search_entries_tsv ON search_entries USING GIN (tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_search_entries_tsv")
    op.execute("ALTER TABLE search_entries DROP COLUMN IF EXISTS tsv")
    op.drop_index("ix_search_entries_source_type", table_name="search_entries")
    op.drop_index("ix_search_entries_group_id", table_name="search_entries")
    op.drop_index("ix_search_entries_organization_id", table_name="search_entries")
    op.drop_index("ix_search_entries_conversation_id", table_name="search_entries")
    op.drop_table("search_entries")
