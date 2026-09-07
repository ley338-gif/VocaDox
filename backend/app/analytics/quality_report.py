"""Post-GA P1-4: the Evaluation Lab's customer-facing quality report —
real Word Error Rate over an admin-selected, explicitly-listed sample of
already-reviewed conversations (never a silently-chosen "favorable"
sample), plus the same extraction-quality metrics `quality_metrics`
already computes, scoped to that exact sample. Nothing here is persisted
(no new table) — the report is computed fresh from current data every
time and is exportable (see app.analytics.router's format=json/pdf/docx),
which is what makes it reproducible: the same conversation_ids, run
again, produce the same report from the same underlying data.

Deliberately reuses `run_vocabulary_comparison`'s "real audio + reviewed
transcript as ground truth" approach (see ADR-0031) rather than the
synthetic fixture every other Evaluation Lab comparison type uses — a
procurement/DPO/EU-AI-Act audience needs real measured numbers on real
(if redacted-of-content) data, not a synthetic benchmark score.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import quality_metrics
from app.analytics.wer import word_error_rate
from app.conversations.models import Conversation
from app.media.models import MediaAsset, MediaKind
from app.providers.speech_to_text import SpeechToTextProvider
from app.providers.storage import StorageProvider
from app.transcription.service import get_active_ready_transcript, list_segments


class _SkipConversation(Exception):
    """Internal control flow only — never escapes generate_quality_report."""


@dataclass(frozen=True, slots=True)
class ConversationWerResult:
    # Identified by id only, deliberately never by title/content — this
    # report is designed to be exported to third parties (procurement,
    # DPO, auditors), so it follows the same "counts/ids/rates only, never
    # transcript/fact/document content" rule every other analytics
    # response in this module follows (see tests/analytics/test_privacy.py).
    conversation_id: uuid.UUID
    word_error_rate: float
    reference_word_count: int


@dataclass(frozen=True, slots=True)
class SkippedConversation:
    conversation_id: uuid.UUID
    reason: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    generated_at: datetime
    speech_provider: str
    speech_model: str
    speech_model_revision: str | None
    conversation_results: list[ConversationWerResult]
    skipped: list[SkippedConversation]
    mean_word_error_rate: float | None
    quality_metrics: dict[str, object]


async def _resolve_ground_truth_and_audio(
    db: AsyncSession, storage: StorageProvider, conversation_id: uuid.UUID
) -> tuple[Conversation, str, str | None, str]:
    """Returns (conversation, normalized_audio_path, language, ground_truth).
    Raises `_SkipConversation` with a human-readable reason for anything
    that makes this conversation unusable as a report sample — mirrors
    `run_vocabulary_comparison`'s own prerequisite checks exactly, but
    skips rather than aborting the whole report."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise _SkipConversation("conversation not found")

    source_media_result = await db.execute(
        select(MediaAsset)
        .where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.SOURCE_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc())
    )
    source_media = source_media_result.scalars().first()
    if source_media is None:
        raise _SkipConversation("no source audio")

    transcript = await get_active_ready_transcript(db, source_media_id=source_media.id)
    if transcript is None:
        raise _SkipConversation("no active, ready transcript")

    segments = await list_segments(db, transcript_id=transcript.id)
    ground_truth = " ".join(s.corrected_text or s.original_text for s in segments)
    if not ground_truth.strip():
        raise _SkipConversation("transcript has no content")

    normalized_result = await db.execute(
        select(MediaAsset)
        .where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.NORMALIZED_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc())
    )
    normalized_media = normalized_result.scalars().first()
    if normalized_media is None:
        raise _SkipConversation("no normalized audio")
    path = await storage.open_path(normalized_media.storage_key)

    return conversation, str(path), transcript.language, ground_truth


async def generate_quality_report(
    db: AsyncSession,
    storage: StorageProvider,
    speech_provider: SpeechToTextProvider,
    *,
    conversation_ids: list[uuid.UUID],
) -> QualityReport:
    status = speech_provider.status()
    results: list[ConversationWerResult] = []
    skipped: list[SkippedConversation] = []
    included_ids: list[uuid.UUID] = []

    for conversation_id in conversation_ids:
        try:
            _conversation, path, language, ground_truth = await _resolve_ground_truth_and_audio(
                db, storage, conversation_id
            )
        except _SkipConversation as exc:
            skipped.append(SkippedConversation(conversation_id=conversation_id, reason=str(exc)))
            continue

        try:
            transcription = await speech_provider.transcribe(path, language_hint=language)
        except Exception as exc:  # noqa: BLE001 - a failed item must be visible, not abort the report
            skipped.append(
                SkippedConversation(
                    conversation_id=conversation_id,
                    reason=f"transcription failed: {type(exc).__name__}: {exc}"[:500],
                )
            )
            continue

        hypothesis = " ".join(seg.text for seg in transcription.segments)
        wer = round(word_error_rate(ground_truth, hypothesis), 4)
        results.append(
            ConversationWerResult(
                conversation_id=conversation_id,
                word_error_rate=wer,
                reference_word_count=len(ground_truth.split()),
            )
        )
        included_ids.append(conversation_id)

    mean_wer = round(sum(r.word_error_rate for r in results) / len(results), 4) if results else None
    # `included_ids` (possibly empty) is passed as-is, never widened to
    # None/"global" — a report that skipped every requested conversation
    # must show empty/zero metrics for exactly that reason, not silently
    # fall back to unrelated organization-wide numbers.
    metrics = await quality_metrics(db, conversation_ids=included_ids)

    return QualityReport(
        generated_at=datetime.now(UTC),
        speech_provider=status.provider,
        speech_model=status.model,
        speech_model_revision=status.model_revision,
        conversation_results=results,
        skipped=skipped,
        mean_word_error_rate=mean_wer,
        quality_metrics=metrics,
    )
