"""known_speakers, conversation_participants.known_speaker_id (post-GA:
persistent cross-conversation speaker identity)

Today a `ConversationParticipant` (and, through it, a `DetectedSpeaker`
assignment) only exists per-conversation — every conversation with the
same person requires re-typing/re-selecting their name from scratch, even
though the same participant (e.g. a staff member who appears in most of
an organization's conversations) recurs constantly.

`known_speakers`: an org-scoped, named identity ("Dr. Müller", "Yvonne")
that persists across conversations. Deliberately metadata-only — no
voice/biometric data is stored here, and nothing auto-matches a detected
speaker's voice to a KnownSpeaker. Real acoustic speaker recognition is a
natural next step (pyannote's diarization output already computes
per-speaker embeddings internally, just currently discarded — see
app.providers.diarization), but Phase 12 Finding #12 (genuine multi-voice
diarization accuracy has never been verified against real distinct
voices, only same-voice-different-playback-rate fixtures) means shipping
automatic identity-matching on top of an unverified pipeline would risk
silently misattributing a real person's identity — a worse failure mode
than "the staff member picks from a dropdown." Deferred, not forgotten.

Adds nullable `conversation_participants.known_speaker_id` — linking a
per-conversation participant to an org-wide KnownSpeaker means the next
conversation can reuse the identity (pick from a list) instead of typing
the name again.

No existing column is dropped or renamed; no existing row's meaning
changes.

Revision ID: 0013_known_speakers
Revises: 0012_operations
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_known_speakers"
down_revision: str | None = "0012_operations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "known_speakers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_known_speakers_organization_id", "known_speakers", ["organization_id"]
    )

    op.add_column(
        "conversation_participants",
        sa.Column("known_speaker_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversation_participants_known_speaker_id",
        "conversation_participants",
        "known_speakers",
        ["known_speaker_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversation_participants_known_speaker_id",
        "conversation_participants",
        ["known_speaker_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_participants_known_speaker_id",
        table_name="conversation_participants",
    )
    op.drop_constraint(
        "fk_conversation_participants_known_speaker_id",
        "conversation_participants",
        type_="foreignkey",
    )
    op.drop_column("conversation_participants", "known_speaker_id")

    op.drop_index("ix_known_speakers_organization_id", table_name="known_speakers")
    op.drop_table("known_speakers")
