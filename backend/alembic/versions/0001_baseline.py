"""baseline (no-op) — establishes the migration chain for Phase 0

No domain tables exist yet (spec §65: domain schema starts Phase 1). This
migration exists solely so `alembic upgrade head` has a revision to run
against a fresh database, proving the migration framework itself is wired
correctly end-to-end.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-17

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
