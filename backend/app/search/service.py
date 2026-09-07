"""Search index maintenance + query (post-GA P0-1). See
`app.search.models.SearchEntry`'s module docstring for the dual-dialect
design (`tsvector`/GIN on real Postgres; a portable `content.ilike`
fallback under the SQLite test suite) and
`docs/architecture/adr/0030-search-index-dual-dialect.md` for the full
reasoning.

Callers upsert one `SearchEntry` per searchable unit whenever that
unit's current, human-visible content changes -- see the call sites in
`app.transcription.service` (segment create/correct),
`app.intelligence.service` (fact create/supersede), and
`app.documents.service` (document compose). Never a batch reindex job:
each write path keeps its own slice of the index current inline, the
same "no separate sync step to forget" principle as this project's
other denormalized fields.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.search.models import SearchEntry, SearchSourceType

_SNIPPET_LENGTH = 220


@dataclass(frozen=True, slots=True)
class SearchHit:
    entry: SearchEntry
    snippet: str
    rank: float


def _dialect_name(session: AsyncSession) -> str:
    bind = session.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


async def upsert_search_entry(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    organization_id: uuid.UUID,
    group_id: uuid.UUID | None,
    source_type: SearchSourceType,
    source_id: uuid.UUID,
    content: str,
) -> SearchEntry:
    """Insert or update the one entry for (source_type, source_id) --
    never accumulates a second row for the same source (see
    `SearchEntry`'s unique constraint), so a re-composed Document or a
    corrected segment replaces its own prior indexed content rather than
    appending a stale duplicate."""
    result = await session.execute(
        select(SearchEntry).where(
            SearchEntry.source_type == source_type.value, SearchEntry.source_id == source_id
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = SearchEntry(
            conversation_id=conversation_id,
            organization_id=organization_id,
            group_id=group_id,
            source_type=source_type.value,
            source_id=source_id,
            content=content,
        )
        session.add(entry)
    else:
        entry.content = content
        entry.group_id = group_id
    await session.flush()
    return entry


async def delete_search_entry(
    session: AsyncSession, *, source_type: SearchSourceType, source_id: uuid.UUID
) -> None:
    """Removes a source's entry entirely -- used when a fact is
    superseded (PR #61) or removed, so search never surfaces content a
    human can no longer see in the Fakten tab/Document."""
    await session.execute(
        delete(SearchEntry).where(
            SearchEntry.source_type == source_type.value, SearchEntry.source_id == source_id
        )
    )


async def delete_search_entries_for_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> None:
    """Used when a conversation is deleted (mirrors the FollowUpTask
    cleanup added in #60 -- a deleted conversation's content must not
    keep surfacing in search)."""
    await session.execute(
        delete(SearchEntry).where(SearchEntry.conversation_id == conversation_id)
    )


async def search_entries(
    session: AsyncSession,
    *,
    query: str,
    organization_ids: set[uuid.UUID] | None,
    group_ids: set[uuid.UUID] | None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SearchHit], int]:
    """`organization_ids=None` means system:admin (no org filter);
    `group_ids=None` means the caller can bypass team scope -- both
    mirror `app.conversations.service.list_conversations`'s own scoping
    convention exactly, including "a team-less entry (group_id IS NULL)
    is visible org-wide"."""
    query = query.strip()
    if not query:
        return [], 0

    base_filters: list[ColumnElement[bool]] = []
    if organization_ids is not None:
        base_filters.append(SearchEntry.organization_id.in_(organization_ids))
    if group_ids is not None:
        base_filters.append(
            or_(SearchEntry.group_id.is_(None), SearchEntry.group_id.in_(group_ids))
        )

    if _dialect_name(session) == "postgresql":
        match_clause = text("search_entries.tsv @@ plainto_tsquery('german', :q)")
        rank_expr = text("ts_rank(search_entries.tsv, plainto_tsquery('german', :q))")
        snippet_expr = text(
            "ts_headline('german', search_entries.content, "
            "plainto_tsquery('german', :q), "
            "'StartSel=✦,StopSel=✦,MaxWords=35,MinWords=15,MaxFragments=1')"
        )
        count_stmt = select(SearchEntry.id).where(match_clause, *base_filters)
        count_result = await session.execute(count_stmt, {"q": query})
        total = len(count_result.all())

        pg_stmt: Select[Any] = (
            select(SearchEntry, rank_expr.label("rank"), snippet_expr.label("snippet"))
            .where(match_clause, *base_filters)
            .order_by(text("rank DESC"))
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(pg_stmt, {"q": query})
        return [
            SearchHit(entry=row.SearchEntry, snippet=row.snippet, rank=row.rank)
            for row in result.all()
        ], total

    # SQLite fallback (test suite only, no real Postgres available) --
    # proves scoping/upsert/ordering behavior without claiming real
    # linguistic full-text matching; see this module's docstring.
    like_filter = SearchEntry.content.ilike(f"%{query}%")
    count_stmt = select(SearchEntry.id).where(like_filter, *base_filters)
    total = len((await session.execute(count_stmt)).all())

    stmt = (
        select(SearchEntry)
        .where(like_filter, *base_filters)
        .order_by(SearchEntry.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    hits = []
    for entry in result.scalars().all():
        idx = entry.content.lower().find(query.lower())
        start = max(0, idx - _SNIPPET_LENGTH // 2) if idx >= 0 else 0
        snippet = entry.content[start : start + _SNIPPET_LENGTH]
        hits.append(SearchHit(entry=entry, snippet=snippet, rank=0.0))
    return hits, total
