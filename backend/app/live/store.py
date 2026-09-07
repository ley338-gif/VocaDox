"""Ephemeral cache-backed storage for one conversation's in-progress live
transcript/draft — same "thin wrapper over CacheBackend" pattern as
`app.identity.sessions.SessionStore`. Nothing here is a database model;
state is lost (by design) if Valkey restarts or the TTL expires, both
acceptable since this is a discardable live-preview aid, never the
system of record.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.platform.valkey.backends import CacheBackend

_KEY_PREFIX = "live:session:"


@dataclass(frozen=True)
class LiveSessionData:
    transcript_text: str
    draft_text: str | None
    chunk_count: int
    transcript_word_count_at_last_draft: int
    updated_at: str


class LiveSessionStore:
    def __init__(self, cache: CacheBackend, *, ttl_seconds: int) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    def _key(self, conversation_id: uuid.UUID) -> str:
        return f"{_KEY_PREFIX}{conversation_id}"

    async def get(self, conversation_id: uuid.UUID) -> LiveSessionData | None:
        raw = await self._cache.get(self._key(conversation_id))
        if raw is None:
            return None
        return LiveSessionData(**json.loads(raw))

    async def set(self, conversation_id: uuid.UUID, data: LiveSessionData) -> None:
        await self._cache.set(
            self._key(conversation_id), json.dumps(asdict(data)), ttl_seconds=self._ttl_seconds
        )

    async def clear(self, conversation_id: uuid.UUID) -> None:
        await self._cache.delete(self._key(conversation_id))

    async def replace_transcript(
        self, conversation_id: uuid.UUID, *, transcript_text: str
    ) -> LiveSessionData:
        existing = await self.get(conversation_id)
        data = LiveSessionData(
            transcript_text=transcript_text,
            draft_text=existing.draft_text if existing else None,
            chunk_count=(existing.chunk_count if existing else 0) + 1,
            transcript_word_count_at_last_draft=(
                existing.transcript_word_count_at_last_draft if existing else 0
            ),
            updated_at=datetime.now(UTC).isoformat(),
        )
        await self.set(conversation_id, data)
        return data

    async def set_draft(
        self, conversation_id: uuid.UUID, *, draft_text: str, transcript_word_count: int
    ) -> LiveSessionData:
        existing = await self.get(conversation_id)
        transcript_text = existing.transcript_text if existing else ""
        chunk_count = existing.chunk_count if existing else 0
        data = LiveSessionData(
            transcript_text=transcript_text,
            draft_text=draft_text,
            chunk_count=chunk_count,
            transcript_word_count_at_last_draft=transcript_word_count,
            updated_at=datetime.now(UTC).isoformat(),
        )
        await self.set(conversation_id, data)
        return data
