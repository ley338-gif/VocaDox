"""transcript_segment_speaker_corrections (per-segment speaker correction)

Adds the audit table for correcting a single transcript segment's
speaker attribution onto a different, already-detected speaker in the
same conversation -- independent of `app.diarization.models
.DetectedSpeaker.display_label` (which relabels a whole detected-speaker
CLUSTER at once). Diarization clusters by voice embedding, not by any
human-obvious trait, so a handful of segments can land in the wrong
cluster even when a human hears the mistake immediately; today the only
correction tool was cluster-wide relabeling, which would also touch
every other, correctly-clustered segment sharing that label.

No existing column is dropped or renamed; no existing row's meaning
changes. `transcript_segments.speaker_id` is updated in place by this
feature -- it is already a plain FK (not a dual original/corrected pair
like `original_text`/`corrected_text`), so this new table is the
correction history, mirroring `transcript_segment_corrections`.

Revision ID: 0016_speaker_corrections
Revises: 0015_conversation_team_scope
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_speaker_corrections"
down_revision: str | None = "0015_conversation_team_scope"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_segment_speaker_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("previous_speaker_id", sa.Uuid(), nullable=True),
        sa.Column("new_speaker_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"], ["transcript_segments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["corrected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["previous_speaker_id"], ["detected_speakers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["new_speaker_id"], ["detected_speakers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcript_segment_speaker_corrections_segment_id",
        "transcript_segment_speaker_corrections",
        ["segment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcript_segment_speaker_corrections_segment_id",
        table_name="transcript_segment_speaker_corrections",
    )
    op.drop_table("transcript_segment_speaker_corrections")
