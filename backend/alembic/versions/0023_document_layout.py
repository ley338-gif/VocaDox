"""document_layout (post-GA: profile/template-driven document rendering
style, e.g. a formal Arztbrief-style layout for a "Medical Consultation"
template vs. the original flat section layout for everything else)

Adds `document_layout` to `template_versions` (which style this
template's TemplateVersion renders as -- source of truth) and to
`document_revisions` (a denormalized snapshot of the resolved value at
compose time, mirroring how `template_version_id` is already snapshotted
there -- see app.documents.service.compose_document).

Both columns are NOT NULL with a `'sections'` server default, so every
existing row (which always used the original flat-section rendering)
keeps that exact behavior with no backfill needed.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0023_document_layout
Revises: 0022_recap_share_links
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_document_layout"
down_revision: str | None = "0022_recap_share_links"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "template_versions",
        sa.Column(
            "document_layout", sa.String(length=32), nullable=False, server_default="sections"
        ),
    )
    op.add_column(
        "document_revisions",
        sa.Column(
            "document_layout", sa.String(length=32), nullable=False, server_default="sections"
        ),
    )


def downgrade() -> None:
    op.drop_column("document_revisions", "document_layout")
    op.drop_column("template_versions", "document_layout")
