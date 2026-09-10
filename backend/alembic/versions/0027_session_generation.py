"""Invalidate existing sessions after password reset or deactivation.

Revision ID: 0027_session_generation
Revises: 0026_protocols
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_session_generation"
down_revision: str | None = "0026_protocols"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_generation", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "session_generation")
