from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SearchResultResponse(BaseModel):
    conversation_id: uuid.UUID
    conversation_title: str
    source_type: str
    source_id: uuid.UUID
    snippet: str
    rank: float
    updated_at: datetime


class SearchResponse(BaseModel):
    items: list[SearchResultResponse]
    total: int
    limit: int
    offset: int
