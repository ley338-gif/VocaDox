"""templates, template_versions, prompts, prompt_versions, model_profile_versions,
processing_profiles, processing_profile_versions (Phase 6) + additive columns
on model_profiles/conversations/processing_runs/document_revisions.

Adds the Template Engine (`templates`/`template_versions`), Prompt
lifecycle (`prompts`/`prompt_versions`), extends Phase 4's `model_profiles`
(new `thinking_mode`/`configuration` columns, both nullable) with a real
version history (`model_profile_versions`), and the new
`processing_profiles`/`processing_profile_versions` system (spec §19). No
existing column is dropped or renamed; every extension is additive and
nullable/defaulted so Phase 4/5 data survives the upgrade unchanged.

Circular FK pairs (`templates.current_published_version_id` <->
`template_versions.template_id`, `prompts.current_published_version_id` <->
`prompt_versions.prompt_id`, `processing_profiles.current_published_version_id`
<-> `processing_profile_versions.processing_profile_id`) are each resolved
the same way Phase 5 resolved `documents`/`document_revisions`: the parent
table is created first with that column nullable and NO FK, the child table
is created next with its FK to the parent, and the FK from the parent's
pointer column is added afterward via `ALTER TABLE`.

Revision ID: 0008_templates_profiles
Revises: 0007_documents_review
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_templates_profiles"
down_revision: str | None = "0007_documents_review"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # -- templates / template_versions ---------------------------------
    op.create_table(
        "templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_templates_key"),
    )
    op.create_index("ix_templates_key", "templates", ["key"], unique=True)

    op.create_table(
        "template_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("extraction_categories", sa.JSON(), nullable=False),
        sa.Column("presentation", sa.JSON(), nullable=False),
        sa.Column("review_rules", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])
    op.create_index("ix_template_versions_status", "template_versions", ["status"])

    op.create_foreign_key(
        "fk_templates_current_published_version_id",
        "templates",
        "template_versions",
        ["current_published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- prompts / prompt_versions --------------------------------------
    op.create_table(
        "prompts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_prompts_key"),
    )
    op.create_index("ix_prompts_key", "prompts", ["key"], unique=True)

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("system_prompt", sa.String(length=4096), nullable=False),
        sa.Column("category_instructions", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_versions_prompt_id", "prompt_versions", ["prompt_id"])
    op.create_index("ix_prompt_versions_status", "prompt_versions", ["status"])

    op.create_foreign_key(
        "fk_prompts_current_published_version_id",
        "prompts",
        "prompt_versions",
        ["current_published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- model_profiles (Phase 4) additive columns + model_profile_versions
    op.add_column("model_profiles", sa.Column("thinking_mode", sa.String(length=32), nullable=True))
    op.add_column("model_profiles", sa.Column("configuration", sa.JSON(), nullable=True))

    op.create_table(
        "model_profile_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_identifier", sa.String(length=256), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("structured_output", sa.Boolean(), nullable=False),
        sa.Column("thinking_mode", sa.String(length=32), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["model_profile_id"], ["model_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_profile_versions_model_profile_id", "model_profile_versions", ["model_profile_id"]
    )

    # -- processing_profiles / processing_profile_versions ---------------
    op.create_table(
        "processing_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("is_system_default", sa.Boolean(), nullable=False),
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_processing_profiles_key"),
    )
    op.create_index("ix_processing_profiles_key", "processing_profiles", ["key"], unique=True)
    op.create_index("ix_processing_profiles_enabled", "processing_profiles", ["enabled"])

    op.create_table(
        "processing_profile_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("processing_profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("speech_provider_config", sa.JSON(), nullable=True),
        sa.Column("diarization_provider_config", sa.JSON(), nullable=True),
        sa.Column("extraction_model_profile_id", sa.Uuid(), nullable=True),
        sa.Column("document_model_profile_id", sa.Uuid(), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("retention_policy_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["processing_profile_id"], ["processing_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["extraction_model_profile_id"], ["model_profiles.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["document_model_profile_id"], ["model_profiles.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_version_id"], ["template_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["prompt_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["retention_policy_id"], ["retention_policies.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_profile_versions_processing_profile_id",
        "processing_profile_versions",
        ["processing_profile_id"],
    )
    op.create_index(
        "ix_processing_profile_versions_status", "processing_profile_versions", ["status"]
    )

    op.create_foreign_key(
        "fk_processing_profiles_current_published_version_id",
        "processing_profiles",
        "processing_profile_versions",
        ["current_published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- conversations: PROCESSING PROFILE + CONVERSATION OVERRIDE layers -
    op.add_column("conversations", sa.Column("processing_profile_id", sa.Uuid(), nullable=True))
    op.add_column("conversations", sa.Column("config_overrides", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_processing_profile_id",
        "conversations",
        "processing_profiles",
        ["processing_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- processing_runs: record which template/prompt/profile version was
    # actually used (spec §43 reproducibility requirement) ----------------
    op.add_column("processing_runs", sa.Column("template_version_id", sa.Uuid(), nullable=True))
    op.add_column("processing_runs", sa.Column("prompt_version_id", sa.Uuid(), nullable=True))
    op.add_column(
        "processing_runs", sa.Column("processing_profile_version_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_processing_runs_template_version_id",
        "processing_runs",
        "template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_processing_runs_prompt_version_id",
        "processing_runs",
        "prompt_versions",
        ["prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_processing_runs_processing_profile_version_id",
        "processing_runs",
        "processing_profile_versions",
        ["processing_profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- document_revisions: which TemplateVersion's presentation actually
    # rendered this revision ----------------------------------------------
    op.add_column(
        "document_revisions", sa.Column("template_version_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_document_revisions_template_version_id",
        "document_revisions",
        "template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_revisions_template_version_id", "document_revisions", type_="foreignkey"
    )
    op.drop_column("document_revisions", "template_version_id")

    op.drop_constraint(
        "fk_processing_runs_processing_profile_version_id", "processing_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_processing_runs_prompt_version_id", "processing_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_processing_runs_template_version_id", "processing_runs", type_="foreignkey"
    )
    op.drop_column("processing_runs", "processing_profile_version_id")
    op.drop_column("processing_runs", "prompt_version_id")
    op.drop_column("processing_runs", "template_version_id")

    op.drop_constraint(
        "fk_conversations_processing_profile_id", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "config_overrides")
    op.drop_column("conversations", "processing_profile_id")

    op.drop_constraint(
        "fk_processing_profiles_current_published_version_id",
        "processing_profiles",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_processing_profile_versions_status", table_name="processing_profile_versions"
    )
    op.drop_index(
        "ix_processing_profile_versions_processing_profile_id",
        table_name="processing_profile_versions",
    )
    op.drop_table("processing_profile_versions")

    op.drop_index("ix_processing_profiles_enabled", table_name="processing_profiles")
    op.drop_index("ix_processing_profiles_key", table_name="processing_profiles")
    op.drop_table("processing_profiles")

    op.drop_index(
        "ix_model_profile_versions_model_profile_id", table_name="model_profile_versions"
    )
    op.drop_table("model_profile_versions")
    op.drop_column("model_profiles", "configuration")
    op.drop_column("model_profiles", "thinking_mode")

    op.drop_constraint("fk_prompts_current_published_version_id", "prompts", type_="foreignkey")
    op.drop_index("ix_prompt_versions_status", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_prompt_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompts_key", table_name="prompts")
    op.drop_table("prompts")

    op.drop_constraint(
        "fk_templates_current_published_version_id", "templates", type_="foreignkey"
    )
    op.drop_index("ix_template_versions_status", table_name="template_versions")
    op.drop_index("ix_template_versions_template_id", table_name="template_versions")
    op.drop_table("template_versions")
    op.drop_index("ix_templates_key", table_name="templates")
    op.drop_table("templates")
