"""documents, document_revisions, fact_corrections tables + review/fact
correction columns (Phase 5)

Adds `documents`/`document_revisions` (app.documents.models),
`fact_corrections` (app.intelligence.models), and extends
`extracted_facts` (review_status/corrected_structured_value/
reviewed_by_user_id/reviewed_at) and `review_issues` (resolved_status/
resolved_fact_id/resolved_by_user_id/resolved_at). No existing column is
dropped or renamed; every extension is additive and nullable/defaulted so
Phase 4 data survives the upgrade unchanged (existing facts/evidence rows
just get `review_status='pending'`).

`documents.current_revision_id` and `document_revisions.document_id` are
mutually referencing FKs — `documents` is created first with that column
nullable and NO FK, `document_revisions` is created next with its FK to
`documents.id`, and the FK from `documents.current_revision_id` to
`document_revisions.id` is added afterward via ALTER TABLE.

Revision ID: 0007_documents_review
Revises: 0006_intelligence_evidence
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_documents_review"
down_revision: str | None = "0006_intelligence_evidence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_revision_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_documents_conversation_id"),
    )
    op.create_index("ix_documents_conversation_id", "documents", ["conversation_id"], unique=True)
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    op.create_table(
        "document_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("structured_content", sa.JSON(), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocking_issue_ids", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_revisions_document_id", "document_revisions", ["document_id"])
    op.create_index("ix_document_revisions_status", "document_revisions", ["status"])
    op.create_index("ix_document_revisions_created_at", "document_revisions", ["created_at"])

    op.create_foreign_key(
        "fk_documents_current_revision_id",
        "documents",
        "document_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "fact_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("previous_structured_value", sa.JSON(), nullable=True),
        sa.Column("new_structured_value", sa.JSON(), nullable=False),
        sa.Column("corrected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fact_id"], ["extracted_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_corrections_fact_id", "fact_corrections", ["fact_id"])

    op.add_column(
        "extracted_facts",
        sa.Column("review_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.add_column(
        "extracted_facts", sa.Column("corrected_structured_value", sa.JSON(), nullable=True)
    )
    op.add_column("extracted_facts", sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "extracted_facts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_extracted_facts_reviewed_by_user_id",
        "extracted_facts",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_extracted_facts_review_status", "extracted_facts", ["review_status"])
    op.alter_column("extracted_facts", "review_status", server_default=None)

    op.add_column(
        "review_issues", sa.Column("resolved_status", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "review_issues", sa.Column("resolved_fact_id", sa.String(length=64), nullable=True)
    )
    op.add_column("review_issues", sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "review_issues", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_review_issues_resolved_by_user_id",
        "review_issues",
        "users",
        ["resolved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_review_issues_resolved_by_user_id", "review_issues", type_="foreignkey"
    )
    op.drop_column("review_issues", "resolved_at")
    op.drop_column("review_issues", "resolved_by_user_id")
    op.drop_column("review_issues", "resolved_fact_id")
    op.drop_column("review_issues", "resolved_status")

    op.drop_index("ix_extracted_facts_review_status", table_name="extracted_facts")
    op.drop_constraint(
        "fk_extracted_facts_reviewed_by_user_id", "extracted_facts", type_="foreignkey"
    )
    op.drop_column("extracted_facts", "reviewed_at")
    op.drop_column("extracted_facts", "reviewed_by_user_id")
    op.drop_column("extracted_facts", "corrected_structured_value")
    op.drop_column("extracted_facts", "review_status")

    op.drop_index("ix_fact_corrections_fact_id", table_name="fact_corrections")
    op.drop_table("fact_corrections")

    op.drop_constraint("fk_documents_current_revision_id", "documents", type_="foreignkey")

    op.drop_index("ix_document_revisions_created_at", table_name="document_revisions")
    op.drop_index("ix_document_revisions_status", table_name="document_revisions")
    op.drop_index("ix_document_revisions_document_id", table_name="document_revisions")
    op.drop_table("document_revisions")

    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_conversation_id", table_name="documents")
    op.drop_table("documents")
