"""vocabulary_entries (post-GA P0-3: custom transcription vocabulary)

Adds the org-scoped, optionally template-scoped custom vocabulary table
-- one entry per (organization, optional template), resolved by
`app.vocabulary.service.resolve_vocabulary` and passed through to
faster-whisper's `hotwords`/`initial_prompt` parameters at transcription
time (see `app.providers.speech_to_text`).

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0018_vocabulary_entries
Revises: 0017_search_entries
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_vocabulary_entries"
down_revision: str | None = "0017_search_entries"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vocabulary_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("initial_prompt", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "template_id", name="uq_vocabulary_org_template"
        ),
    )
    op.create_index(
        "ix_vocabulary_entries_organization_id", "vocabulary_entries", ["organization_id"]
    )
    op.create_index("ix_vocabulary_entries_template_id", "vocabulary_entries", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_vocabulary_entries_template_id", table_name="vocabulary_entries")
    op.drop_index("ix_vocabulary_entries_organization_id", table_name="vocabulary_entries")
    op.drop_table("vocabulary_entries")
