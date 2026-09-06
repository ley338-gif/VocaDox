"""recaps, recap_revisions (post-GA: shareable participant-facing recap)

A `Recap` is a NEW, separate artifact type from `Document`/`DocumentRevision`
(app.documents) — a short, warm, plain-language narrative meant to be
shared with the OTHER party in a conversation (e.g. a patient after-visit
summary, a meeting recap for an external attendee), always explicitly
labeled as AI-generated. This does **not** relax the hard constraint on
`app.documents.service.compose_document` ("never an LLM 'write a report'
call", spec's rejected architecture for the official record Document,
see that module's docstring / ADR-0027) — that constraint is scoped to
the Document/DocumentRevision domain specifically. A Recap is a distinct,
lower-stakes, explicitly-disclosed-as-AI artifact, generated from the
conversation's already-composed Document content (never raw transcript
directly), and — matching every other AI-produced artifact in this
project — a human must explicitly approve it (`recap:approve`) before it
is considered ready to share; the AI never self-approves here either.

Mirrors `Document`/`DocumentRevision`'s proven immutable-revision shape
(see app/documents/models.py) rather than a single mutable row: `Recap`
is the stable per-conversation identity, `RecapRevision` is one
immutable-once-APPROVED snapshot. Re-generating always INSERTs a new
revision, never mutates an existing one.

No existing table/column is touched.

Revision ID: 0014_recaps
Revises: 0013_known_speakers
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_recaps"
down_revision: str | None = "0013_known_speakers"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("current_revision_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )

    op.create_table(
        "recap_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recap_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_identifier", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["recap_id"], ["recaps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recap_revisions_recap_id", "recap_revisions", ["recap_id"])

    op.create_foreign_key(
        "fk_recaps_current_revision_id",
        "recaps",
        "recap_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_recaps_current_revision_id", "recaps", type_="foreignkey")
    op.drop_index("ix_recap_revisions_recap_id", table_name="recap_revisions")
    op.drop_table("recap_revisions")
    op.drop_table("recaps")
