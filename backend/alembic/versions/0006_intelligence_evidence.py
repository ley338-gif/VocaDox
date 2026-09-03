"""intelligence, evidence, review, and model-profile tables (Phase 4)

Adds `model_profiles` (app.profiles.models), `extracted_facts`
(app.intelligence.models), `fact_evidence` (app.evidence.models), and
`review_issues` (app.review.models). See
docs/architecture/domain-model.md's "Source -> Facts -> Document
provenance" section for the intended shape. No existing table is altered.

Revision ID: 0006_intelligence_evidence
Revises: 0005_processing_outbox
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_intelligence_evidence"
down_revision: str | None = "0005_processing_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_identifier", sa.String(length=256), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("structured_output", sa.Boolean(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_profiles_purpose", "model_profiles", ["purpose"])
    op.create_index("ix_model_profiles_enabled", "model_profiles", ["enabled"])

    op.create_table(
        "extracted_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("structured_value", sa.JSON(), nullable=False),
        sa.Column("certainty", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extracted_facts_conversation_id", "extracted_facts", ["conversation_id"])
    op.create_index("ix_extracted_facts_category", "extracted_facts", ["category"])
    op.create_index("ix_extracted_facts_fact_type", "extracted_facts", ["fact_type"])
    op.create_index("ix_extracted_facts_status", "extracted_facts", ["status"])
    op.create_index("ix_extracted_facts_created_at", "extracted_facts", ["created_at"])

    op.create_table(
        "fact_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_segment_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fact_id"], ["extracted_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["transcript_segment_id"], ["transcript_segments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_evidence_fact_id", "fact_evidence", ["fact_id"])
    op.create_index(
        "ix_fact_evidence_transcript_segment_id", "fact_evidence", ["transcript_segment_id"]
    )

    op.create_table(
        "review_issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("issue_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("uncertainty_category", sa.String(length=32), nullable=True),
        sa.Column("related_fact_ids", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issue_metadata", sa.JSON(), nullable=True),
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
    )
    op.create_index("ix_review_issues_conversation_id", "review_issues", ["conversation_id"])
    op.create_index("ix_review_issues_issue_type", "review_issues", ["issue_type"])
    op.create_index("ix_review_issues_severity", "review_issues", ["severity"])
    op.create_index("ix_review_issues_status", "review_issues", ["status"])
    op.create_index("ix_review_issues_created_at", "review_issues", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_issues_created_at", table_name="review_issues")
    op.drop_index("ix_review_issues_status", table_name="review_issues")
    op.drop_index("ix_review_issues_severity", table_name="review_issues")
    op.drop_index("ix_review_issues_issue_type", table_name="review_issues")
    op.drop_index("ix_review_issues_conversation_id", table_name="review_issues")
    op.drop_table("review_issues")

    op.drop_index("ix_fact_evidence_transcript_segment_id", table_name="fact_evidence")
    op.drop_index("ix_fact_evidence_fact_id", table_name="fact_evidence")
    op.drop_table("fact_evidence")

    op.drop_index("ix_extracted_facts_created_at", table_name="extracted_facts")
    op.drop_index("ix_extracted_facts_status", table_name="extracted_facts")
    op.drop_index("ix_extracted_facts_fact_type", table_name="extracted_facts")
    op.drop_index("ix_extracted_facts_category", table_name="extracted_facts")
    op.drop_index("ix_extracted_facts_conversation_id", table_name="extracted_facts")
    op.drop_table("extracted_facts")

    op.drop_index("ix_model_profiles_enabled", table_name="model_profiles")
    op.drop_index("ix_model_profiles_purpose", table_name="model_profiles")
    op.drop_table("model_profiles")
