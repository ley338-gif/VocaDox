"""Post-GA P2-1: live draft regeneration gating — unit-level, since
FakeSpeechProvider's deterministic ~10-word output can never cross the
word-count thresholds via the HTTP ingest path (it ignores audio content,
so the "transcript" never actually grows). Exercises
app.live.service.maybe_regenerate_live_draft directly against a
FakeCacheBackend-backed store and FakeLLMProvider.
"""

from __future__ import annotations

import uuid

from app.live.service import maybe_regenerate_live_draft
from app.live.store import LiveSessionStore
from app.providers.llm import FakeLLMProvider

from tests.identity.conftest import FakeCacheBackend


async def test_no_draft_below_minimum_word_count() -> None:
    store = LiveSessionStore(FakeCacheBackend(), ttl_seconds=60)
    conversation_id = uuid.uuid4()
    session = await store.replace_transcript(conversation_id, transcript_text="a few words only")

    result = await maybe_regenerate_live_draft(
        store, FakeLLMProvider(), conversation_id=conversation_id, session=session
    )
    assert result.draft_text is None


async def test_draft_generated_once_minimum_word_count_reached() -> None:
    store = LiveSessionStore(FakeCacheBackend(), ttl_seconds=60)
    conversation_id = uuid.uuid4()
    long_text = " ".join(f"word{i}" for i in range(45))
    session = await store.replace_transcript(conversation_id, transcript_text=long_text)

    result = await maybe_regenerate_live_draft(
        store, FakeLLMProvider(), conversation_id=conversation_id, session=session
    )
    assert result.draft_text is not None
    assert result.transcript_word_count_at_last_draft == 45


async def test_draft_not_regenerated_before_word_delta_threshold() -> None:
    store = LiveSessionStore(FakeCacheBackend(), ttl_seconds=60)
    conversation_id = uuid.uuid4()
    long_text = " ".join(f"word{i}" for i in range(45))
    session = await store.replace_transcript(conversation_id, transcript_text=long_text)
    first = await maybe_regenerate_live_draft(
        store, FakeLLMProvider(), conversation_id=conversation_id, session=session
    )

    # Transcript unchanged (still 45 words) -- must not regenerate again.
    unchanged = await store.replace_transcript(conversation_id, transcript_text=long_text)
    second = await maybe_regenerate_live_draft(
        store, FakeLLMProvider(), conversation_id=conversation_id, session=unchanged
    )
    assert second.draft_text == first.draft_text
    assert second.transcript_word_count_at_last_draft == first.transcript_word_count_at_last_draft

    # Growing well past the regeneration delta must trigger a fresh draft.
    grown_text = " ".join(f"word{i}" for i in range(120))
    grown_session = await store.replace_transcript(conversation_id, transcript_text=grown_text)
    third = await maybe_regenerate_live_draft(
        store, FakeLLMProvider(), conversation_id=conversation_id, session=grown_session
    )
    assert third.transcript_word_count_at_last_draft == 120
