"""speech-to-text, diarization & transcript alignment

Adds the Phase 3 processing layer: `processing_runs`, `processing_jobs`,
`transcripts`, `transcript_segments`, `transcript_segment_corrections`,
`detected_speakers`, `diarization_segments`. No Phase-4 facts/evidence/
document tables. Existing Phase-2 `conversations`/`media_assets` rows are
untouched by this migration (no column changes on those tables — the
Conversation state machine's new statuses are free-string values on the
existing `conversations.status` column, requiring no schema change).

Revision ID: 0004_speech_diarization
Revises: 0003_conversation_capture
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_speech_diarization"
down_revision: str | None = "0003_conversation_capture"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_media_id", sa.Uuid(), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("configuration_snapshot", sa.JSON(), nullable=True),
        sa.Column("application_version", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.String(length=1024), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_media_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_runs_conversation_id", "processing_runs", ["conversation_id"])
    op.create_index("ix_processing_runs_source_media_id", "processing_runs", ["source_media_id"])
    op.create_index("ix_processing_runs_run_type", "processing_runs", ["run_type"])

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_media_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("failure_class", sa.String(length=32), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.String(length=1024), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_run_id", sa.Uuid(), nullable=True),
        sa.Column("job_metadata", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_media_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_jobs_conversation_id", "processing_jobs", ["conversation_id"])
    op.create_index("ix_processing_jobs_source_media_id", "processing_jobs", ["source_media_id"])
    op.create_index("ix_processing_jobs_job_type", "processing_jobs", ["job_type"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_media_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_safe", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_media_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcripts_conversation_id", "transcripts", ["conversation_id"])
    op.create_index("ix_transcripts_source_media_id", "transcripts", ["source_media_id"])
    op.create_index("ix_transcripts_status", "transcripts", ["status"])
    op.create_index("ix_transcripts_created_at", "transcripts", ["created_at"])

    op.create_table(
        "detected_speakers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("diarization_run_id", sa.Uuid(), nullable=True),
        sa.Column("internal_label", sa.String(length=64), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=True),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["diarization_run_id"], ["processing_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["conversation_participants.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detected_speakers_conversation_id", "detected_speakers", ["conversation_id"])

    op.create_table(
        "diarization_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("diarization_run_id", sa.Uuid(), nullable=False),
        sa.Column("speaker_id", sa.Uuid(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_overlap", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["diarization_run_id"], ["processing_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["speaker_id"], ["detected_speakers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diarization_segments_diarization_run_id", "diarization_segments", ["diarization_run_id"]
    )
    op.create_index("ix_diarization_segments_speaker_id", "diarization_segments", ["speaker_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("speaker_id", sa.Uuid(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("words", sa.JSON(), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("alignment_quality", sa.String(length=16), nullable=False),
        sa.Column("review_flag", sa.Boolean(), nullable=False),
        sa.Column("review_flag_reason", sa.String(length=255), nullable=True),
        sa.Column("speech_run_id", sa.Uuid(), nullable=True),
        sa.Column("diarization_run_id", sa.Uuid(), nullable=True),
        sa.Column("alignment_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["speaker_id"], ["detected_speakers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["speech_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["diarization_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["alignment_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"])
    op.create_index("ix_transcript_segments_speaker_id", "transcript_segments", ["speaker_id"])
    op.create_index(
        "ix_transcript_segments_review_status", "transcript_segments", ["review_status"]
    )

    op.create_table(
        "transcript_segment_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("previous_corrected_text", sa.Text(), nullable=True),
        sa.Column("new_corrected_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcript_segment_corrections_segment_id",
        "transcript_segment_corrections",
        ["segment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcript_segment_corrections_segment_id",
        table_name="transcript_segment_corrections",
    )
    op.drop_table("transcript_segment_corrections")

    op.drop_index("ix_transcript_segments_review_status", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_speaker_id", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_transcript_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")

    op.drop_index("ix_diarization_segments_speaker_id", table_name="diarization_segments")
    op.drop_index(
        "ix_diarization_segments_diarization_run_id", table_name="diarization_segments"
    )
    op.drop_table("diarization_segments")

    op.drop_index("ix_detected_speakers_conversation_id", table_name="detected_speakers")
    op.drop_table("detected_speakers")

    op.drop_index("ix_transcripts_created_at", table_name="transcripts")
    op.drop_index("ix_transcripts_status", table_name="transcripts")
    op.drop_index("ix_transcripts_source_media_id", table_name="transcripts")
    op.drop_index("ix_transcripts_conversation_id", table_name="transcripts")
    op.drop_table("transcripts")

    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_job_type", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_source_media_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_conversation_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")

    op.drop_index("ix_processing_runs_run_type", table_name="processing_runs")
    op.drop_index("ix_processing_runs_source_media_id", table_name="processing_runs")
    op.drop_index("ix_processing_runs_conversation_id", table_name="processing_runs")
    op.drop_table("processing_runs")
