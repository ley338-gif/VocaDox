"""users.first_name, users.last_name, users.gender, users.avatar_asset_key
(post-GA: fuller admin user-management UI -- edit a user's name/gender/
avatar, not just deactivate them).

All four columns are nullable and additive: `display_name` (the one
existing, mandatory name field) is untouched and every existing
row/caller keeps working unchanged. No backfill needed -- every
pre-existing user simply has all four as NULL until an admin edits them.

Revision ID: 0025_user_profile_fields
Revises: 0024_template_org_freeform
Create Date: 2026-09-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_user_profile_fields"
down_revision: str | None = "0024_template_org_freeform"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("avatar_asset_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_asset_key")
    op.drop_column("users", "gender")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
