"""model_profile_lifecycle_events, evaluation_runs (Phase 8) + additive
lifecycle_status column on model_profiles.

Phase 8 (spec §50/§51, roadmap §73) adds:

- `model_profiles.lifecycle_status`: additive, nullable-with-server-default
  column carrying the spec §51 lifecycle
  (AVAILABLE -> TESTING -> PILOT -> PRODUCTION -> RETIRED, with rollback to
  any prior status). Every existing Phase 4/6 `model_profiles` row defaults
  to `"available"` on upgrade — no data loss, no behavior change for any
  code path that doesn't read this new column.
- `model_profile_lifecycle_events`: an append-only audit trail of every
  lifecycle transition (from_status/to_status/actor/note/checklist flags),
  mirroring the existing `model_profile_versions`/`fact_corrections`
  "one row per event, never updated" pattern — this is what makes rollback
  possible without destroying history (spec: "don't destroy history").
- `evaluation_runs`: one row per Evaluation Lab comparison (model-vs-model
  or prompt-vs-prompt), storing the fixture reference, both subjects'
  configuration (ids/names/config only — never transcript content) and
  both subjects' measured results (facts/evidence/contradiction/JSON-
  validity/latency), so a comparison result is inspectable/auditable after
  the fact, not just shown once and discarded.

No existing column is dropped or renamed; every extension is additive and
defaulted so Phase 0-7 data survives the upgrade unchanged.

Revision ID: 0009_analytics_evaluation
Revises: 0008_templates_profiles
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_analytics_evaluation"
down_revision: str | None = "0008_templates_profiles"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # -- model_profiles: additive lifecycle_status column ------------------
    op.add_column(
        "model_profiles",
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default="available",
        ),
    )
    op.create_index(
        "ix_model_profiles_lifecycle_status", "model_profiles", ["lifecycle_status"]
    )

    # -- model_profile_lifecycle_events -------------------------------------
    op.create_table(
        "model_profile_lifecycle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("is_rollback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=1024), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_profile_id"], ["model_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_profile_lifecycle_events_model_profile_id",
        "model_profile_lifecycle_events",
        ["model_profile_id"],
    )

    # -- evaluation_runs ------------------------------------------------------
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fixture_key", sa.String(length=128), nullable=False),
        sa.Column("subject_a", sa.JSON(), nullable=False),
        sa.Column("subject_b", sa.JSON(), nullable=False),
        sa.Column("result_a", sa.JSON(), nullable=True),
        sa.Column("result_b", sa.JSON(), nullable=True),
        sa.Column("error_message_safe", sa.String(length=1024), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_run_type", "evaluation_runs", ["run_type"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_run_type", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index(
        "ix_model_profile_lifecycle_events_model_profile_id",
        table_name="model_profile_lifecycle_events",
    )
    op.drop_table("model_profile_lifecycle_events")

    op.drop_index("ix_model_profiles_lifecycle_status", table_name="model_profiles")
    op.drop_column("model_profiles", "lifecycle_status")
