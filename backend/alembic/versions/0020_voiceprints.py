"""voiceprints (post-GA P1-2: voiceprint enrollment for known speakers)

Adds the storage needed for confidence-scored recurring-speaker
suggestions -- see `app.people.models.KnownSpeaker` and
`app.diarization.models.DetectedSpeaker`'s docstrings:

- `known_speakers.voiceprint_embedding`/`voiceprint_sample_count`/
  `voiceprint_updated_at`: the running-average pyannote embedding for a
  person, written only by an explicit human enrollment action.
- `detected_speakers.embedding`: the diarization provider's raw
  per-speaker embedding for this run, when available.
- `detected_speakers.suggested_known_speaker_id`/`suggested_confidence`:
  a computer-generated *candidate* match a human must explicitly accept
  before it becomes a real assignment -- never a silent identity match.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0020_voiceprints
Revises: 0019_ask_queries
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_voiceprints"
down_revision: str | None = "0019_ask_queries"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("known_speakers", sa.Column("voiceprint_embedding", sa.JSON(), nullable=True))
    op.add_column(
        "known_speakers",
        sa.Column(
            "voiceprint_sample_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "known_speakers",
        sa.Column("voiceprint_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column("detected_speakers", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column(
        "detected_speakers", sa.Column("suggested_known_speaker_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "detected_speakers", sa.Column("suggested_confidence", sa.Float(), nullable=True)
    )
    op.create_foreign_key(
        "fk_detected_speakers_suggested_known_speaker_id",
        "detected_speakers",
        "known_speakers",
        ["suggested_known_speaker_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_detected_speakers_suggested_known_speaker_id",
        "detected_speakers",
        type_="foreignkey",
    )
    op.drop_column("detected_speakers", "suggested_confidence")
    op.drop_column("detected_speakers", "suggested_known_speaker_id")
    op.drop_column("detected_speakers", "embedding")

    op.drop_column("known_speakers", "voiceprint_updated_at")
    op.drop_column("known_speakers", "voiceprint_sample_count")
    op.drop_column("known_speakers", "voiceprint_embedding")
