"""REST endpoints for transcript + processing: trigger processing, poll
job status, read/correct the transcript. Every route enforces Permission +
Organization Membership + Conversation's Organization via
`app.conversations.authz`, matching the Phase 2 pattern exactly — a
transcript is never reachable except through its (authorized) conversation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.authz import authorize_conversation_access
from app.core.ai_providers import get_queue_backend, get_speech_provider
from app.identity.deps import get_current_user, require_csrf
from app.identity.models import User
from app.media.models import MediaAsset, MediaKind
from app.platform.config import get_settings
from app.platform.db.session import get_session
from app.platform.valkey.backends import QueueBackend
from app.processing.models import JobType, ProcessingJob, ProcessingStatus
from app.processing.orchestrator import start_transcription
from app.processing.service import (
    cancel_queued_job,
    count_active_jobs_for_conversation,
    create_and_enqueue_job,
)
from app.providers.speech_to_text import SpeechToTextProvider
from app.transcription.models import SegmentReviewStatus, Transcript, TranscriptSegment
from app.transcription.schemas import (
    ProcessingJobResponse,
    ProcessingStatusResponse,
    ProcessRequest,
    SegmentCorrectionRequest,
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from app.transcription.service import correct_segment, list_segments, set_review_status

router = APIRouter(prefix="/conversations", tags=["transcription"])

_MAX_ACTIVE_JOBS_ERROR = "too many active processing jobs for this conversation"


async def _get_source_media_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> MediaAsset:
    result = await db.execute(
        select(MediaAsset)
        .where(
            MediaAsset.conversation_id == conversation_id,
            MediaAsset.kind == MediaKind.SOURCE_AUDIO.value,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at.desc())
    )
    media = result.scalars().first()
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no source audio for this conversation"
        )
    return media


async def _get_transcript_or_404(db: AsyncSession, conversation_id: uuid.UUID) -> Transcript:
    result = await db.execute(
        select(Transcript).where(
            Transcript.conversation_id == conversation_id, Transcript.is_active.is_(True)
        )
    )
    transcript = result.scalars().first()
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transcript not found")
    return transcript


@router.post(
    "/{conversation_id}/process/transcript",
    response_model=TranscriptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_transcript_endpoint(
    conversation_id: uuid.UUID,
    body: ProcessRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    queue: QueueBackend = Depends(get_queue_backend),
    speech_provider: SpeechToTextProvider = Depends(get_speech_provider),
    _csrf: None = Depends(require_csrf),
) -> TranscriptResponse:
    """Explicit user action to start processing — never triggered
    automatically on upload (spec, "Triggering processing")."""
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="transcript:process"
    )
    source_media = await _get_source_media_or_404(db, conversation_id)

    settings = get_settings()
    active_count = await count_active_jobs_for_conversation(db, conversation_id=conversation_id)
    if active_count >= settings.max_active_processing_jobs_per_conversation:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_MAX_ACTIVE_JOBS_ERROR
        )

    provider_status = speech_provider.status()
    transcript = await start_transcription(
        db,
        queue,
        conversation=conversation,
        source_media=source_media,
        requested_by=user,
        diarize=body.diarize,
        language_hint=body.language_hint,
        min_speakers=body.min_speakers,
        max_speakers=body.max_speakers,
        reprocess=body.reprocess,
        speech_provider_name=provider_status.provider,
        speech_model=provider_status.model,
        speech_model_revision=provider_status.model_revision,
    )
    await db.commit()
    return TranscriptResponse.model_validate(transcript)


@router.get("/{conversation_id}/processing", response_model=ProcessingStatusResponse)
async def get_processing_status_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ProcessingStatusResponse:
    conversation = await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="processing:read"
    )
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.conversation_id == conversation_id)
        .order_by(ProcessingJob.queued_at.desc())
    )
    jobs = result.scalars().all()
    return ProcessingStatusResponse(
        conversation_status=conversation.status,
        jobs=[ProcessingJobResponse.model_validate(j) for j in jobs],
    )


@router.post("/{conversation_id}/processing/retry", response_model=ProcessingJobResponse)
async def retry_processing_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    queue: QueueBackend = Depends(get_queue_backend),
    _csrf: None = Depends(require_csrf),
) -> ProcessingJobResponse:
    """Re-queue the most recent terminally-FAILED job for this conversation
    as a brand new job (spec: explicit retries, not hidden endless retry)."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="processing:retry"
    )
    result = await db.execute(
        select(ProcessingJob)
        .where(
            ProcessingJob.conversation_id == conversation_id,
            ProcessingJob.status == ProcessingStatus.FAILED.value,
        )
        .order_by(ProcessingJob.completed_at.desc())
    )
    failed_job = result.scalars().first()
    if failed_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no failed job to retry")

    new_job = await create_and_enqueue_job(
        db,
        queue,
        conversation_id=failed_job.conversation_id,
        source_media_id=failed_job.source_media_id,
        job_type=JobType(failed_job.job_type),
        created_by_user_id=user.id,
        job_metadata=failed_job.job_metadata,
    )
    await record_event(
        db,
        event_type="processing.retried",
        user_id=user.id,
        event_metadata={"job_id": str(new_job.id), "retried_from_job_id": str(failed_job.id)},
    )
    await db.commit()
    return ProcessingJobResponse.model_validate(new_job)


@router.post(
    "/{conversation_id}/processing/{job_id}/cancel",
    response_model=ProcessingJobResponse,
)
async def cancel_processing_job_endpoint(
    conversation_id: uuid.UUID,
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> ProcessingJobResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="processing:retry"
    )
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.conversation_id == conversation_id
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    cancelled = await cancel_queued_job(db, job)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only a QUEUED job can be cancelled (a RUNNING job cannot be safely "
            "interrupted in this phase)",
        )
    await db.commit()
    return ProcessingJobResponse.model_validate(job)


@router.get("/{conversation_id}/transcript", response_model=TranscriptResponse)
async def get_transcript_endpoint(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> TranscriptResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="transcript:read"
    )
    transcript = await _get_transcript_or_404(db, conversation_id)
    return TranscriptResponse.model_validate(transcript)


@router.get(
    "/{conversation_id}/transcript/segments", response_model=list[TranscriptSegmentResponse]
)
async def list_transcript_segments_endpoint(
    conversation_id: uuid.UUID,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[TranscriptSegmentResponse]:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="transcript:read"
    )
    transcript = await _get_transcript_or_404(db, conversation_id)
    segments = await list_segments(db, transcript_id=transcript.id)
    if q:
        needle = q.lower()
        segments = [
            s
            for s in segments
            if needle in s.original_text.lower()
            or (s.corrected_text and needle in s.corrected_text.lower())
        ]
    return [TranscriptSegmentResponse.model_validate(s) for s in segments]


async def _get_segment_or_404(
    db: AsyncSession, conversation_id: uuid.UUID, segment_id: uuid.UUID
) -> TranscriptSegment:
    transcript = await _get_transcript_or_404(db, conversation_id)
    result = await db.execute(
        select(TranscriptSegment).where(
            TranscriptSegment.id == segment_id, TranscriptSegment.transcript_id == transcript.id
        )
    )
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="segment not found")
    return segment


@router.patch(
    "/{conversation_id}/transcript/segments/{segment_id}",
    response_model=TranscriptSegmentResponse,
)
async def correct_segment_endpoint(
    conversation_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: SegmentCorrectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> TranscriptSegmentResponse:
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="transcript:correct"
    )
    segment = await _get_segment_or_404(db, conversation_id, segment_id)

    if body.corrected_text is not None:
        await correct_segment(db, segment, new_text=body.corrected_text, user_id=user.id)
        await record_event(
            db,
            event_type="transcript.segment_corrected",
            user_id=user.id,
            event_metadata={"segment_id": str(segment.id)},
        )
    elif body.review_status is not None:
        await set_review_status(db, segment, status=SegmentReviewStatus(body.review_status))

    await db.commit()
    return TranscriptSegmentResponse.model_validate(segment)


@router.get("/{conversation_id}/transcript/export")
async def export_transcript_endpoint(
    conversation_id: uuid.UUID,
    format: str = "text",  # noqa: A002 - matches the query param name intentionally
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Plain text / JSON export, no generated summaries (spec: "Transcript
    export"). Respects the same authorization as every other transcript
    read."""
    await authorize_conversation_access(
        db, user=user, conversation_id=conversation_id, permission_code="transcript:read"
    )
    transcript = await _get_transcript_or_404(db, conversation_id)
    segments = await list_segments(db, transcript_id=transcript.id)

    if format == "json":
        import json as _json

        payload = {
            "transcript_id": str(transcript.id),
            "language": transcript.language,
            "segments": [
                {
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "speaker_id": str(s.speaker_id) if s.speaker_id else None,
                    "text": s.corrected_text or s.original_text,
                }
                for s in segments
            ],
        }
        return Response(content=_json.dumps(payload, indent=2), media_type="application/json")

    if format == "markdown":
        lines = [
            f"**[{_fmt_ts(s.start_ms)}]** {s.corrected_text or s.original_text}" for s in segments
        ]
        return Response(content="\n\n".join(lines), media_type="text/markdown")

    lines = [f"[{_fmt_ts(s.start_ms)}] {s.corrected_text or s.original_text}" for s in segments]
    return Response(content="\n".join(lines), media_type="text/plain")


def _fmt_ts(ms: int) -> str:
    total_seconds = ms // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
