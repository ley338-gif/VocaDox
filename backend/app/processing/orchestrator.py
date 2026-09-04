"""Processing pipeline orchestration: the API-facing entry point
(`start_transcription`) plus the four stage executors the worker calls
after dequeuing a job. This is the one place that ties together
app.media, app.providers, app.transcription, app.diarization, and
app.conversations' state machine for Phase 3's async pipeline.

Chaining: NORMALIZE -> {TRANSCRIBE, DIARIZE} -> ALIGN. TRANSCRIBE and
DIARIZE both depend only on the normalized asset, not on each other, so
they run independently (possibly on separate worker services — see
app.processing.queues). Whichever of the two finishes second triggers
ALIGN (see `_maybe_trigger_align`), so no polling/waiting job is ever
needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.conversations.models import Conversation, ConversationStatus
from app.conversations.state_machine import is_valid_transition
from app.diarization.service import persist_diarization_result
from app.identity.models import User
from app.media.metadata import extract_audio_metadata
from app.media.models import MediaAsset, MediaKind, MediaSourceType
from app.media.normalizer import MediaNormalizer, NormalizationInput
from app.platform.valkey.backends import QueueBackend
from app.platform.version import APPLICATION_VERSION
from app.processing.models import JobType, ProcessingJob, ProcessingRun, RunStatus, RunType
from app.processing.service import create_and_enqueue_job, get_active_job
from app.providers.diarization import DiarizationProvider
from app.providers.llm import LLMProvider
from app.providers.speech_to_text import SpeechToTextProvider
from app.providers.storage import StorageProvider
from app.transcription.alignment import align_transcript
from app.transcription.models import Transcript
from app.transcription.serialization import (
    diarization_result_from_dict,
    diarization_result_to_dict,
    transcription_result_from_dict,
    transcription_result_to_dict,
)
from app.transcription.service import (
    create_transcript,
    get_active_ready_transcript,
    get_active_transcript,
    mark_transcript_processing,
    persist_aligned_segments,
)

NORMALIZATION_PROFILE = "default"
NORMALIZER_VERSION = "ffmpeg-16k-mono-pcm16-v1"


async def _get_normalized_media(
    session: AsyncSession, *, source_media_id: uuid.UUID
) -> MediaAsset | None:
    """Idempotency for normalization: reuse a prior successful output keyed
    on source_media_id + normalizer_version + profile instead of creating
    a duplicate derived asset on retry."""
    result = await session.execute(
        select(ProcessingRun).where(
            ProcessingRun.source_media_id == source_media_id,
            ProcessingRun.run_type == RunType.NORMALIZATION.value,
            ProcessingRun.status == RunStatus.SUCCEEDED.value,
        )
    )
    for run in result.scalars().all():
        snapshot = run.configuration_snapshot or {}
        if snapshot.get("normalizer_version") != NORMALIZER_VERSION:
            continue
        if snapshot.get("normalization_profile") != NORMALIZATION_PROFILE:
            continue
        media_id = snapshot.get("output_media_id")
        if not media_id:
            continue
        media = await session.get(MediaAsset, uuid.UUID(media_id))
        if media is not None and media.deleted_at is None:
            return media
    return None


async def _transition_conversation(
    session: AsyncSession, conversation: Conversation, target: ConversationStatus
) -> None:
    current = ConversationStatus(conversation.status)
    if current == target:
        return
    if is_valid_transition(current, target):
        conversation.status = target.value
        await session.flush()
    # Silently skip an invalid transition rather than raising — a
    # conversation already marked READY/FAILED/DELETED by a concurrent
    # request should not have a lagging worker callback crash the job.


async def start_transcription(
    session: AsyncSession,
    queue: QueueBackend,
    *,
    conversation: Conversation,
    source_media: MediaAsset,
    requested_by: User,
    diarize: bool = True,
    language_hint: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    reprocess: bool = False,
    speech_provider_name: str,
    speech_model: str,
    speech_model_revision: str | None,
) -> Transcript:
    """API entry point for `POST /conversations/{id}/process/transcript`.
    Idempotent unless `reprocess=True` (spec: "Job idempotency" /
    "Reprocessing")."""

    if not reprocess:
        active = await get_active_transcript(session, source_media_id=source_media.id)
        if active is not None:
            return active
        ready = await get_active_ready_transcript(session, source_media_id=source_media.id)
        if (
            ready is not None
            and ready.provider == speech_provider_name
            and ready.model == speech_model
            and ready.model_revision == speech_model_revision
        ):
            return ready
    else:
        # Reprocess: deactivate the previous active transcript (kept, not
        # deleted — processing history survives) so exactly one transcript
        # is "active" per source at a time.
        for prior in (
            await session.execute(
                select(Transcript).where(
                    Transcript.source_media_id == source_media.id, Transcript.is_active.is_(True)
                )
            )
        ).scalars().all():
            prior.is_active = False
        await session.flush()

    transcript = await create_transcript(
        session,
        conversation_id=conversation.id,
        source_media_id=source_media.id,
        provider=speech_provider_name,
        model=speech_model,
        model_revision=speech_model_revision,
    )

    normalized = await _get_normalized_media(session, source_media_id=source_media.id)
    job_metadata: dict = {"diarize": diarize}
    if language_hint:
        job_metadata["language_hint"] = language_hint
    if min_speakers:
        job_metadata["min_speakers"] = min_speakers
    if max_speakers:
        job_metadata["max_speakers"] = max_speakers

    if normalized is None:
        existing_normalize_job = await get_active_job(
            session, source_media_id=source_media.id, job_type=JobType.NORMALIZE
        )
        if existing_normalize_job is None:
            await create_and_enqueue_job(
                session,
                queue,
                conversation_id=conversation.id,
                source_media_id=source_media.id,
                job_type=JobType.NORMALIZE,
                created_by_user_id=requested_by.id,
                job_metadata=job_metadata,
            )
        await _transition_conversation(session, conversation, ConversationStatus.NORMALIZING)
    else:
        job_metadata["normalized_media_id"] = str(normalized.id)
        await create_and_enqueue_job(
            session,
            queue,
            conversation_id=conversation.id,
            source_media_id=source_media.id,
            job_type=JobType.TRANSCRIBE,
            created_by_user_id=requested_by.id,
            job_metadata=job_metadata,
        )
        if diarize:
            await create_and_enqueue_job(
                session,
                queue,
                conversation_id=conversation.id,
                source_media_id=source_media.id,
                job_type=JobType.DIARIZE,
                created_by_user_id=requested_by.id,
                job_metadata=job_metadata,
            )
        await _transition_conversation(session, conversation, ConversationStatus.TRANSCRIBING)

    await record_event(
        session,
        event_type="processing.started",
        user_id=requested_by.id,
        event_metadata={
            "conversation_id": str(conversation.id),
            "source_media_id": str(source_media.id),
            "transcript_id": str(transcript.id),
            "reprocess": reprocess,
        },
    )
    return transcript


# -- Stage executors, called by app.workers.processing_worker ----------------


async def execute_normalize(
    session: AsyncSession,
    storage: StorageProvider,
    normalizer: MediaNormalizer,
    job: ProcessingJob,
) -> uuid.UUID:
    """Returns the ProcessingRun id. Raises on failure — caller (worker)
    classifies and applies retry policy."""
    source = await session.get(MediaAsset, job.source_media_id)
    if source is None:
        raise ValueError(f"source media {job.source_media_id} not found")

    run = ProcessingRun(
        conversation_id=job.conversation_id,
        source_media_id=source.id,
        run_type=RunType.NORMALIZATION.value,
        status=RunStatus.RUNNING.value,
        provider=type(normalizer).__name__,
        model="n/a",
        application_version=APPLICATION_VERSION,
        configuration_snapshot={
            "normalizer_version": NORMALIZER_VERSION,
            "normalization_profile": NORMALIZATION_PROFILE,
        },
    )
    session.add(run)
    await session.flush()

    source_path = await storage.open_path(source.storage_key)
    data = Path(source_path).read_bytes()  # noqa: ASYNC240 - reads a locally-spooled file once
    result = await normalizer.normalize(
        NormalizationInput(
            data=data, content_type=source.content_type, container=source.container
        )
    )

    metadata = extract_audio_metadata(result.data, container=result.container or "wav")

    derived = MediaAsset(
        conversation_id=job.conversation_id,
        kind=MediaKind.NORMALIZED_AUDIO.value,
        source_type=MediaSourceType.DERIVED.value,
        storage_key="",
        original_filename=None,
        content_type=result.content_type,
        size_bytes=len(result.data),
        sha256=__import__("hashlib").sha256(result.data).hexdigest(),
        duration_ms=result.duration_ms or metadata.duration_ms,
        sample_rate=result.sample_rate or metadata.sample_rate,
        channels=result.channels or metadata.channels,
        codec=result.codec,
        container=result.container,
        derived_from_media_id=source.id,
        created_by_user_id=source.created_by_user_id,
    )
    session.add(derived)
    await session.flush()
    namespace = f"organizations/derived/conversations/{job.conversation_id.hex}/derived"
    storage_key = await storage.save(
        result.data, suffix=f".{result.container or 'bin'}", namespace=namespace
    )
    derived.storage_key = storage_key
    await session.flush()

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    run.configuration_snapshot = {
        **(run.configuration_snapshot or {}),
        "output_media_id": str(derived.id),
    }
    await session.flush()

    await record_event(
        session,
        event_type="processing.completed",
        event_metadata={"processing_run_id": str(run.id), "run_type": "normalization"},
    )
    return run.id


async def trigger_post_normalize(
    session: AsyncSession,
    queue: QueueBackend,
    job: ProcessingJob,
    *,
    normalized_media_id: uuid.UUID,
) -> None:
    """Called by the worker after a NORMALIZE job succeeds: enqueues
    TRANSCRIBE (and DIARIZE, if requested) against the freshly-normalized
    media. Idempotent via get_or_create_job's active-job check."""
    metadata = dict(job.job_metadata or {})
    metadata["normalized_media_id"] = str(normalized_media_id)
    diarize = metadata.get("diarize", True)

    if await get_active_job(
        session, source_media_id=job.source_media_id, job_type=JobType.TRANSCRIBE
    ) is None:
        await create_and_enqueue_job(
            session,
            queue,
            conversation_id=job.conversation_id,
            source_media_id=job.source_media_id,
            job_type=JobType.TRANSCRIBE,
            created_by_user_id=job.created_by_user_id,
            job_metadata=metadata,
        )
    if diarize and await get_active_job(
        session, source_media_id=job.source_media_id, job_type=JobType.DIARIZE
    ) is None:
        await create_and_enqueue_job(
            session,
            queue,
            conversation_id=job.conversation_id,
            source_media_id=job.source_media_id,
            job_type=JobType.DIARIZE,
            created_by_user_id=job.created_by_user_id,
            job_metadata=metadata,
        )
    conversation = await session.get(Conversation, job.conversation_id)
    if conversation is not None:
        await _transition_conversation(session, conversation, ConversationStatus.TRANSCRIBING)


async def _resolve_normalized_media(session: AsyncSession, job: ProcessingJob) -> MediaAsset:
    metadata = job.job_metadata or {}
    media_id = metadata.get("normalized_media_id")
    if media_id:
        media = await session.get(MediaAsset, uuid.UUID(media_id))
        if media is not None:
            return media
    media = await _get_normalized_media(session, source_media_id=job.source_media_id)
    if media is None:
        raise ValueError("normalized media not found — NORMALIZE must succeed before this stage")
    return media


async def execute_transcribe(
    session: AsyncSession,
    storage: StorageProvider,
    speech_provider: SpeechToTextProvider,
    job: ProcessingJob,
) -> uuid.UUID:
    normalized = await _resolve_normalized_media(session, job)
    path = await storage.open_path(normalized.storage_key)

    status = speech_provider.status()
    run = ProcessingRun(
        conversation_id=job.conversation_id,
        source_media_id=job.source_media_id,
        run_type=RunType.SPEECH_TO_TEXT.value,
        status=RunStatus.RUNNING.value,
        provider=status.provider,
        model=status.model,
        model_revision=status.model_revision,
        application_version=APPLICATION_VERSION,
        configuration_snapshot={
            "device": status.device,
            "language_hint": (job.job_metadata or {}).get("language_hint"),
        },
    )
    session.add(run)
    await session.flush()

    result = await speech_provider.transcribe(
        str(path), language_hint=(job.job_metadata or {}).get("language_hint")
    )

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    run.raw_output = transcription_result_to_dict(result)
    await session.flush()

    transcript = await get_active_transcript(session, source_media_id=job.source_media_id)
    if transcript is not None:
        await mark_transcript_processing(
            session, transcript, processing_run_id=run.id, language=result.language
        )

    await record_event(
        session,
        event_type="processing.completed",
        event_metadata={"processing_run_id": str(run.id), "run_type": "speech_to_text"},
    )
    return run.id


async def execute_diarize(
    session: AsyncSession,
    storage: StorageProvider,
    diarization_provider: DiarizationProvider,
    job: ProcessingJob,
) -> uuid.UUID:
    normalized = await _resolve_normalized_media(session, job)
    path = await storage.open_path(normalized.storage_key)
    metadata = job.job_metadata or {}

    status = diarization_provider.status()
    run = ProcessingRun(
        conversation_id=job.conversation_id,
        source_media_id=job.source_media_id,
        run_type=RunType.DIARIZATION.value,
        status=RunStatus.RUNNING.value,
        provider=status.provider,
        model=status.model,
        model_revision=status.model_revision,
        application_version=APPLICATION_VERSION,
        configuration_snapshot={
            "min_speakers": metadata.get("min_speakers"),
            "max_speakers": metadata.get("max_speakers"),
        },
    )
    session.add(run)
    await session.flush()

    result = await diarization_provider.diarize(
        str(path),
        min_speakers=metadata.get("min_speakers"),
        max_speakers=metadata.get("max_speakers"),
    )

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    run.raw_output = diarization_result_to_dict(result)
    await session.flush()

    await persist_diarization_result(
        session, conversation_id=job.conversation_id, diarization_run_id=run.id, result=result
    )

    await record_event(
        session,
        event_type="diarization.completed",
        event_metadata={
            "processing_run_id": str(run.id),
            "speaker_count": result.speaker_count,
        },
    )
    return run.id


async def _latest_run(
    session: AsyncSession, *, source_media_id: uuid.UUID, run_type: RunType
) -> ProcessingRun | None:
    result = await session.execute(
        select(ProcessingRun)
        .where(
            ProcessingRun.source_media_id == source_media_id,
            ProcessingRun.run_type == run_type.value,
            ProcessingRun.status == RunStatus.SUCCEEDED.value,
        )
        .order_by(ProcessingRun.completed_at.desc())
    )
    return result.scalars().first()


async def execute_align(session: AsyncSession, job: ProcessingJob) -> uuid.UUID:
    speech_run = await _latest_run(
        session, source_media_id=job.source_media_id, run_type=RunType.SPEECH_TO_TEXT
    )
    if speech_run is None or speech_run.raw_output is None:
        raise ValueError("no successful SPEECH_TO_TEXT run to align from")

    diarize_requested = (job.job_metadata or {}).get("diarize", True)
    diarization_run = None
    if diarize_requested:
        diarization_run = await _latest_run(
            session, source_media_id=job.source_media_id, run_type=RunType.DIARIZATION
        )

    transcription_result = transcription_result_from_dict(speech_run.raw_output)
    diarization_result = (
        diarization_result_from_dict(diarization_run.raw_output)
        if diarization_run is not None and diarization_run.raw_output
        else None
    )

    aligned = align_transcript(transcription_result, diarization_result)

    run = ProcessingRun(
        conversation_id=job.conversation_id,
        source_media_id=job.source_media_id,
        run_type=RunType.ALIGNMENT.value,
        status=RunStatus.RUNNING.value,
        provider="vocadox-alignment",
        model="word-overlap-v1",
        application_version=APPLICATION_VERSION,
        configuration_snapshot={"confident_threshold": 0.66},
    )
    session.add(run)
    await session.flush()

    speaker_label_to_id: dict[str, uuid.UUID] = {}
    if diarization_run is not None:
        from app.diarization.models import DetectedSpeaker

        result = await session.execute(
            select(DetectedSpeaker).where(DetectedSpeaker.diarization_run_id == diarization_run.id)
        )
        speaker_label_to_id = {s.internal_label: s.id for s in result.scalars().all()}

    transcript_result = await session.execute(
        select(Transcript).where(
            Transcript.source_media_id == job.source_media_id, Transcript.is_active.is_(True)
        )
    )
    transcript = transcript_result.scalars().first()
    if transcript is None:
        raise ValueError("no active Transcript to attach aligned segments to")

    await persist_aligned_segments(
        session,
        transcript,
        aligned,
        speech_run_id=speech_run.id,
        diarization_run_id=diarization_run.id if diarization_run else None,
        alignment_run_id=run.id,
        speaker_label_to_id=speaker_label_to_id,
    )

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    await session.flush()

    conversation = await session.get(Conversation, job.conversation_id)
    if conversation is not None:
        await _transition_conversation(session, conversation, ConversationStatus.ALIGNING)
        await _transition_conversation(session, conversation, ConversationStatus.READY)

    await record_event(
        session,
        event_type="transcript.created",
        event_metadata={"transcript_id": str(transcript.id), "processing_run_id": str(run.id)},
    )
    return run.id


async def maybe_trigger_align(
    session: AsyncSession, queue: QueueBackend, job: ProcessingJob
) -> None:
    """Called after TRANSCRIBE or DIARIZE succeeds: if the pipeline is now
    ready for alignment (the other required stage has already succeeded,
    or diarization wasn't requested), enqueue ALIGN exactly once."""
    diarize_requested = (job.job_metadata or {}).get("diarize", True)

    speech_run = await _latest_run(
        session, source_media_id=job.source_media_id, run_type=RunType.SPEECH_TO_TEXT
    )
    if speech_run is None:
        return  # TRANSCRIBE hasn't succeeded yet — DIARIZE's caller will retry later

    if diarize_requested:
        diarization_run = await _latest_run(
            session, source_media_id=job.source_media_id, run_type=RunType.DIARIZATION
        )
        if diarization_run is None:
            return  # waiting on DIARIZE

    existing = await get_active_job(
        session, source_media_id=job.source_media_id, job_type=JobType.ALIGN
    )
    if existing is not None:
        return

    await create_and_enqueue_job(
        session,
        queue,
        conversation_id=job.conversation_id,
        source_media_id=job.source_media_id,
        job_type=JobType.ALIGN,
        created_by_user_id=job.created_by_user_id,
        job_metadata=job.job_metadata,
    )


# -- Phase 4: extraction (explicit-trigger only, never auto-chained from
# ALIGN — spec: "explicit trigger, not automatic") -------------------------


async def start_extraction(
    session: AsyncSession,
    queue: QueueBackend,
    *,
    conversation: Conversation,
    source_media: MediaAsset,
    requested_by: User,
) -> ProcessingJob:
    """API entry point for `POST /conversations/{id}/process/extract`. A
    conversation must be READY (a completed, active Transcript must
    exist) — extraction never runs against a transcript still being
    produced. Always creates a fresh job (re-extraction simply creates new
    ExtractedFact rows via a new ProcessingRun; nothing is deleted, matching
    the Phase 3 "processing history is never destroyed" precedent)."""
    transcript = await get_active_ready_transcript(session, source_media_id=source_media.id)
    if transcript is None:
        raise ValueError("conversation has no active, ready transcript to extract facts from")

    job = await create_and_enqueue_job(
        session,
        queue,
        conversation_id=conversation.id,
        source_media_id=source_media.id,
        job_type=JobType.EXTRACT,
        created_by_user_id=requested_by.id,
        job_metadata={"transcript_id": str(transcript.id)},
    )
    await _transition_conversation(session, conversation, ConversationStatus.EXTRACTING)

    await record_event(
        session,
        event_type="extraction.started",
        user_id=requested_by.id,
        event_metadata={
            "conversation_id": str(conversation.id),
            "transcript_id": str(transcript.id),
            "job_id": str(job.id),
        },
    )
    return job


async def execute_extract(
    session: AsyncSession,
    llm_provider: LLMProvider,
    job: ProcessingJob,
) -> uuid.UUID:
    from app.conversations.models import Conversation
    from app.intelligence.service import run_extraction
    from app.profiles.models import ModelProfile, ModelProfilePurpose
    from app.profiles.resolver import NoSystemDefaultProfileError, resolve_effective_config
    from app.profiles.service import get_active_profile
    from app.providers.llm import LLMModelUnavailableError
    from app.templates.models import PromptVersion, TemplateVersion

    metadata = job.job_metadata or {}
    transcript_id = metadata.get("transcript_id")
    transcript = (
        await session.get(Transcript, uuid.UUID(transcript_id)) if transcript_id else None
    )
    if transcript is None:
        transcript = await get_active_ready_transcript(
            session, source_media_id=job.source_media_id
        )
    if transcript is None:
        raise ValueError("no active, ready transcript to extract from")

    # Phase 6: resolve the effective configuration hierarchy (spec §20) for
    # this conversation — which template/prompt/extraction-model actually
    # apply, and which layer (system default / processing profile /
    # conversation override) decided each. Falls back to the pre-Phase-6
    # get_active_profile()-only behavior if no ProcessingProfile is seeded
    # at all (e.g. an older installation mid-upgrade before the Phase 6
    # seed has run) rather than hard-failing extraction.
    conversation = await session.get(Conversation, job.conversation_id)
    assert conversation is not None
    template_version: TemplateVersion | None = None
    prompt_version: PromptVersion | None = None
    processing_profile_version_id: uuid.UUID | None = None
    profile: ModelProfile | None = None
    try:
        effective = await resolve_effective_config(session, conversation)
        processing_profile_version_id = effective.processing_profile_version_id
        template_version = await session.get(TemplateVersion, effective.template_version_id)
        if effective.prompt_version_id is not None:
            prompt_version = await session.get(PromptVersion, effective.prompt_version_id)
        if effective.extraction_model_profile_id is not None:
            profile = await session.get(ModelProfile, effective.extraction_model_profile_id)
    except NoSystemDefaultProfileError:
        pass

    if profile is None:
        profile = await get_active_profile(session, purpose=ModelProfilePurpose.EXTRACTION)
    if profile is None:
        raise LLMModelUnavailableError(
            "no enabled extraction ModelProfile configured — run `python -m app.profiles.seed`"
        )

    status = llm_provider.status()
    run = ProcessingRun(
        conversation_id=job.conversation_id,
        source_media_id=job.source_media_id,
        run_type=RunType.EXTRACTION.value,
        status=RunStatus.RUNNING.value,
        provider=status.provider,
        model=status.model,
        model_revision=status.model_revision,
        application_version=APPLICATION_VERSION,
        template_version_id=template_version.id if template_version else None,
        prompt_version_id=prompt_version.id if prompt_version else None,
        processing_profile_version_id=processing_profile_version_id,
        configuration_snapshot={
            "model_profile_id": str(profile.id),
            "temperature": profile.temperature,
        },
    )
    session.add(run)
    await session.flush()

    outcome = await run_extraction(
        session,
        conversation_id=job.conversation_id,
        transcript=transcript,
        processing_run_id=run.id,
        provider=llm_provider,
        profile=profile,
        template_version=template_version,
        system_prompt=prompt_version.system_prompt if prompt_version else None,
        category_instruction_overrides=prompt_version.category_instructions
        if prompt_version
        else None,
    )

    run.status = RunStatus.SUCCEEDED.value
    run.completed_at = datetime.now(UTC)
    run.raw_output = {
        "facts_created": outcome.facts_created,
        "review_issues_created": outcome.review_issues_created,
        "facts_by_category": outcome.facts_by_category,
    }
    await session.flush()

    conversation = await session.get(Conversation, job.conversation_id)
    if conversation is not None:
        await _transition_conversation(session, conversation, ConversationStatus.READY)

    # event_metadata carries only counts/ids, never fact content or
    # transcript text (spec §63).
    await record_event(
        session,
        event_type="extraction.completed",
        event_metadata={
            "processing_run_id": str(run.id),
            "conversation_id": str(job.conversation_id),
            "facts_created": outcome.facts_created,
            "review_issues_created": outcome.review_issues_created,
        },
    )
    return run.id
