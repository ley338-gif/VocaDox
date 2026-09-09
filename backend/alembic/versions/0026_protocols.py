"""protocols, protocol_revisions, protocol_sections, protocol_items,
protocol_sources (post-GA: the Protokoll tab -- a structured,
chronological representation of a conversation, distinct from both
Transkript and Dokumentation -- see
docs/architecture/adr/0042-protokoll.md).

Mirrors `documents`/`document_revisions`' shape (Document/DocumentRevision,
app.documents.models) for the identity/revision pair, and
`fact_evidence`'s shape (app.evidence.models) for `protocol_sources`.
`protocols.current_revision_id` -> `protocol_revisions.id` and
`protocol_revisions.protocol_id` -> `protocols.id` is a circular FK pair
by design (same as `documents`/`document_revisions`), so
`protocols.current_revision_id`'s FK constraint is added after both
tables exist.

A brand-new domain -- no existing table/column is touched, no backfill
needed.

Revision ID: 0026_protocols
Revises: 0025_user_profile_fields
Create Date: 2026-09-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_protocols"
down_revision: str | None = "0025_user_profile_fields"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "protocols",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("current_revision_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_protocols_conversation_id", "protocols", ["conversation_id"])

    op.create_table(
        "protocol_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_protocol_revisions_protocol_id", "protocol_revisions", ["protocol_id"])
    op.create_index("ix_protocol_revisions_status", "protocol_revisions", ["status"])
    op.create_index("ix_protocol_revisions_created_at", "protocol_revisions", ["created_at"])

    op.create_foreign_key(
        "fk_protocols_current_revision_id",
        "protocols",
        "protocol_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "protocol_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_revision_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("manually_edited", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["protocol_revision_id"], ["protocol_revisions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_protocol_sections_protocol_revision_id", "protocol_sections", ["protocol_revision_id"]
    )

    op.create_table(
        "protocol_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_section_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("responsible_label", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.String(length=64), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("manually_edited", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["protocol_section_id"], ["protocol_sections.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_protocol_items_protocol_section_id", "protocol_items", ["protocol_section_id"]
    )

    op.create_table(
        "protocol_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_section_id", sa.Uuid(), nullable=True),
        sa.Column("protocol_item_id", sa.Uuid(), nullable=True),
        sa.Column("transcript_segment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["protocol_section_id"], ["protocol_sections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["protocol_item_id"], ["protocol_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transcript_segment_id"], ["transcript_segments.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "(protocol_section_id IS NOT NULL) != (protocol_item_id IS NOT NULL)",
            name="ck_protocol_source_exactly_one_parent",
        ),
    )
    op.create_index(
        "ix_protocol_sources_protocol_section_id", "protocol_sources", ["protocol_section_id"]
    )
    op.create_index(
        "ix_protocol_sources_protocol_item_id", "protocol_sources", ["protocol_item_id"]
    )
    op.create_index(
        "ix_protocol_sources_transcript_segment_id", "protocol_sources", ["transcript_segment_id"]
    )


def downgrade() -> None:
    op.drop_table("protocol_sources")
    op.drop_table("protocol_items")
    op.drop_table("protocol_sections")
    op.drop_constraint("fk_protocols_current_revision_id", "protocols", type_="foreignkey")
    op.drop_table("protocol_revisions")
    op.drop_table("protocols")
