"""templates.organization_id, template_versions.document_body,
template_versions.letterhead_logo_asset_key (post-GA: org-editable
templates -- a "freeform" document layout with placeholder substitution
and an optional uploaded letterhead logo, plus light organization
tagging for admin-authored templates)

`templates.organization_id` is nullable: NULL means a global template
available to every organization (every pre-existing seeded template
keeps this), non-NULL just tags which organization a globally-
permissioned admin created/assigned a custom template for -- not a new
per-org authz/isolation layer (see app.templates.router's docstring).

`template_versions.document_body`/`letterhead_logo_asset_key` are both
nullable and unused by the existing "sections"/"letter" document
layouts -- only a new "freeform" layout reads them (see
app.documents.placeholders / app.documents.service.compose_document).

No existing column is dropped or renamed; no existing row's meaning
changes; no backfill needed.

Revision ID: 0024_template_org_freeform
Revises: 0023_document_layout
Create Date: 2026-09-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_template_org_freeform"
down_revision: str | None = "0023_document_layout"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_templates_organization_id",
        "templates",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_templates_organization_id", "templates", ["organization_id"])

    op.add_column("template_versions", sa.Column("document_body", sa.Text(), nullable=True))
    op.add_column(
        "template_versions",
        sa.Column("letterhead_logo_asset_key", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("template_versions", "letterhead_logo_asset_key")
    op.drop_column("template_versions", "document_body")

    op.drop_index("ix_templates_organization_id", table_name="templates")
    op.drop_constraint("fk_templates_organization_id", "templates", type_="foreignkey")
    op.drop_column("templates", "organization_id")
