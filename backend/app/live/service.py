"""Post-GA P2-1: live transcript + live draft business logic.

**Streaming approach, and why**: the browser's `MediaRecorder` only
produces a fully self-decodable audio file from the FIRST emitted chunk
onward (later timeslices are raw continuation clusters, not independent
files) — so the frontend sends the WHOLE recording-so-far on every
periodic flush, not a delta since the last one (see
`frontend/src/recording/useRecorder.ts`'s `getLiveChunkBlob`). This
service re-runs the configured speech provider on that growing prefix
each time and REPLACES the cached live transcript wholesale, rather than
appending independently-transcribed fragments — the latter would
mis-transcribe words split across a chunk boundary, which whole-prefix
re-transcription avoids entirely. Cost grows with recording length; this
is a disclosed, accepted trade-off for a short-recording live preview,
not the algorithm the final, authoritative pass uses (that one aligns
real fixed audio once, after recording stops — see
`app.processing.orchestrator.execute_transcribe`).

**Live draft**: a coarser-cadence (word-count-gated, not every chunk),
plain-text, unstructured LLM summary of the transcript-so-far — never
the same structured, evidence-linked extraction the real pipeline
performs (`app.intelligence.service`). It is explicitly provisional and
carries no evidence links, because a mid-recording transcript has no
final, reviewable segment boundaries yet to link evidence to. Live draft
generation is skipped entirely once the transcript is too short to be
worth summarizing (`_MIN_WORDS_FOR_DRAFT`) and is re-triggered only after
the transcript has grown by `_DRAFT_REGENERATION_WORD_DELTA` more words,
keeping LLM calls infrequent relative to the 5-15s transcript cadence.
"""

from __future__ import annotations

import uuid

from app.live.store import LiveSessionData, LiveSessionStore
from app.providers.llm import LLMProvider
from app.providers.speech_to_text import SpeechToTextProvider
from app.providers.storage import StorageProvider

_MIN_WORDS_FOR_DRAFT = 40
_DRAFT_REGENERATION_WORD_DELTA = 60

_DRAFT_SYSTEM_PROMPT = (
    "You are drafting a SHORT, PROVISIONAL bullet-point outline in German "
    "of a conversation transcript that is still being recorded. Base it "
    "ONLY on the text given -- never invent anything not present in it. "
    "Keep it to at most 5 short bullet points. This is explicitly a "
    "preliminary draft that will be superseded once the recording is "
    "complete and properly reviewed."
)


async def ingest_live_chunk(
    store: LiveSessionStore,
    storage: StorageProvider,
    speech_provider: SpeechToTextProvider,
    *,
    conversation_id: uuid.UUID,
    audio_bytes: bytes,
    suffix: str,
    language_hint: str | None,
) -> LiveSessionData:
    """Transcribes the given (whole-recording-so-far) audio and replaces
    the cached live transcript with the result."""
    storage_key = await storage.save(audio_bytes, suffix=suffix, namespace="live-chunks")
    try:
        path = await storage.open_path(storage_key)
        result = await speech_provider.transcribe(str(path), language_hint=language_hint)
    finally:
        await storage.delete(storage_key)

    transcript_text = " ".join(segment.text for segment in result.segments).strip()
    return await store.replace_transcript(conversation_id, transcript_text=transcript_text)


async def maybe_regenerate_live_draft(
    store: LiveSessionStore,
    llm_provider: LLMProvider,
    *,
    conversation_id: uuid.UUID,
    session: LiveSessionData,
) -> LiveSessionData:
    """Regenerates the live draft only if the transcript has grown enough
    since the last draft to be worth another LLM call -- returns the
    session unchanged otherwise."""
    word_count = len(session.transcript_text.split())
    if word_count < _MIN_WORDS_FOR_DRAFT:
        return session
    # The delta-growth gate only applies once a first draft already
    # exists -- otherwise a transcript that crosses the minimum but not
    # yet the (larger) regeneration delta would never get its first draft
    # at all.
    if (
        session.draft_text is not None
        and word_count - session.transcript_word_count_at_last_draft
        < _DRAFT_REGENERATION_WORD_DELTA
    ):
        return session

    response = await llm_provider.complete(
        f"Transcript so far:\n{session.transcript_text}", system_prompt=_DRAFT_SYSTEM_PROMPT
    )
    return await store.set_draft(
        conversation_id, draft_text=response.text, transcript_word_count=word_count
    )
