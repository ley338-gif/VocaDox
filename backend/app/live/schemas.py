"""API response schema for the live transcript/draft (post-GA P2-1)."""

from __future__ import annotations

from pydantic import BaseModel


class LiveSessionResponse(BaseModel):
    transcript_text: str
    draft_text: str | None
    chunk_count: int
    updated_at: str
