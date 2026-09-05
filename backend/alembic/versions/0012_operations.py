"""retention_policies.delete_transcript, backup_records,
retention_cleanup_runs, retention_cleanup_items (Phase 11: Operations)

Phase 11 (spec §56/§57/§64, roadmap §73) adds:

- `retention_policies.delete_transcript`: extends the Phase 2 retention
  model (retention_days/delete_source_media/delete_derived_media/active)
  with the one additional trigger the "zero retention" pattern (Audio ->
  Processing -> Document -> Audio DELETE -> Transcript DELETE) needs.
  Nullable=False with server_default=false so every existing row keeps
  its exact prior (no transcript deletion) behavior.
- `backup_records`: one row per backup attempt (metadata only, never the
  backup bytes themselves).
- `retention_cleanup_runs` / `retention_cleanup_items`: the audit trail
  for the real, automated Retention Cleanup Worker — one run row per
  invocation, one item row per individual physical deletion (or, in
  dry-run mode, per deletion that would have happened).

No existing column is dropped or renamed beyond the one additive column
above; every Phase 0-10 row/table is otherwise unaffected.

Revision ID: 0012_operations
Revises: 0011_integrations
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_operations"
down_revision: str | None = "0011_integrations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retention_policies",
        sa.Column(
            "delete_transcript", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    op.create_table(
        "backup_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("storage_path", sa.String(length=2048), nullable=False),
        sa.Column("database_dump_bytes", sa.BigInteger(), nullable=True),
        sa.Column("media_archive_bytes", sa.BigInteger(), nullable=True),
        sa.Column("media_file_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_records_status", "backup_records", ["status"])
    op.create_index("ix_backup_records_started_at", "backup_records", ["started_at"])

    op.create_table(
        "retention_cleanup_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column(
            "conversations_evaluated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("items_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_freed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_cleanup_runs_status", "retention_cleanup_runs", ["status"])
    op.create_index(
        "ix_retention_cleanup_runs_started_at", "retention_cleanup_runs", ["started_at"]
    )

    op.create_table(
        "retention_cleanup_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("retention_policy_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=True),
        sa.Column("transcript_id", sa.Uuid(), nullable=True),
        sa.Column("bytes_freed", sa.BigInteger(), nullable=True),
        sa.Column("segments_deleted", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["retention_cleanup_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["retention_policy_id"], ["retention_policies.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_retention_cleanup_items_run_id", "retention_cleanup_items", ["run_id"]
    )
    op.create_index(
        "ix_retention_cleanup_items_conversation_id",
        "retention_cleanup_items",
        ["conversation_id"],
    )
    op.create_index(
        "ix_retention_cleanup_items_action", "retention_cleanup_items", ["action"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retention_cleanup_items_action", table_name="retention_cleanup_items"
    )
    op.drop_index(
        "ix_retention_cleanup_items_conversation_id", table_name="retention_cleanup_items"
    )
    op.drop_index("ix_retention_cleanup_items_run_id", table_name="retention_cleanup_items")
    op.drop_table("retention_cleanup_items")

    op.drop_index(
        "ix_retention_cleanup_runs_started_at", table_name="retention_cleanup_runs"
    )
    op.drop_index("ix_retention_cleanup_runs_status", table_name="retention_cleanup_runs")
    op.drop_table("retention_cleanup_runs")

    op.drop_index("ix_backup_records_started_at", table_name="backup_records")
    op.drop_index("ix_backup_records_status", table_name="backup_records")
    op.drop_table("backup_records")

    op.drop_column("retention_policies", "delete_transcript")
