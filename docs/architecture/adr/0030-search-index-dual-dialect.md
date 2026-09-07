# 0030 — Search index: Postgres `tsvector`, SQLite `ILIKE` fallback in tests; pgvector deferred

## Status
Accepted (2026-09-07). Post-GA, roadmap item P0-1.

## Context

Full-text search over transcript segments, extracted facts, and
documents was VocaDox's most-cited tender-blocker in the 2026-09-07
competitor analysis: `GET /conversations` only ever filtered
`Conversation.title.ilike(...)`, nothing else. Two design questions had
to be settled before implementation: (1) Postgres full-text search vs.
pgvector semantic search, and (2) how a Postgres-only feature coexists
with this project's test suite, which runs entirely against an
in-memory SQLite database (`Base.metadata.create_all`, never Alembic) —
see `tests/conversations/conftest.py`'s `app_env` fixture.

## Decision

**1. Postgres `tsvector`/GIN, not pgvector, for this feature.** The
practical need (P0-1) is keyword/phrase search a user recognizes from
what was actually said — `tsvector` with the `german` text-search
configuration answers that directly, ships in every Postgres VocaDox
already requires, and adds no new runtime dependency or network call
(ADR-0007: air-gapped). pgvector would add an extension dependency, an
embedding model to run at index time, and answers a different question
("semantically similar", not "contains these words") that P0-1 doesn't
ask for. Semantic retrieval is deferred to P1-1 ("Ask VocaDox"), where
it's evaluated together with that feature's own evidence-citation
requirement rather than bolted onto keyword search.

**2. The generated `tsvector` column and its GIN index are raw DDL in
the Alembic migration, never mapped on the SQLAlchemy model.**
`app.search.models.SearchEntry` only maps portable columns (`content`
as `Text`, plus the denormalized scoping columns). The migration adds
`tsv tsvector GENERATED ALWAYS AS (to_tsvector('german', content))
STORED` and its GIN index via `op.execute(...)` after the ORM-portable
`create_table`. This is safe because every Alembic migration in this
project already targets real Postgres only (the "Alembic migration
(real Postgres)" CI job; the SQLite test DB is built straight from
`Base.metadata`, never runs Alembic) — so there is no dialect branch to
get wrong inside the migration itself.

**3. `app.search.service.search_entries` branches on
`session.get_bind().dialect.name`.** On Postgres: a raw
`tsv @@ plainto_tsquery('german', :q)` predicate, `ts_rank` for
ordering, `ts_headline` for snippets. On SQLite (test suite only): a
plain `content.ilike(f"%{query}%")` predicate, no ranking, a naive
substring-centered snippet. The SQLite path exists to give real,
deterministic test coverage of everything search-shaped that isn't the
linguistic matching itself — org/team scoping, upsert-not-duplicate
behavior, pagination, cross-conversation isolation — the same "tests
never require the real thing, but must prove the real integration
points are wired correctly" precedent already established by
`FakeSpeechProvider`/`FakeDiarizationProvider`/`FakeLLMProvider`. It
never claims to exercise real German morphology/stemming; that only
happens against real Postgres in a running deployment.

## Consequences

- No new dependency, no new container, no new network call.
- A future semantic-search feature (if P1-1 needs one) makes its own
  pgvector-vs-alternative decision fresh, informed by that feature's own
  license/on-prem-footprint review — not constrained by this one.
- Anyone adding a new searchable source type must remember: index
  maintenance is inline at each write path (no reindex job exists), and
  a superseded/removed/corrected fact's entry must be updated or deleted
  at the same time the fact itself changes (see `app.intelligence
  .service`'s `_supersede_previous_facts` and `app.documents.service
  .resolve_review_issue`) — the same "the source of truth writes both,
  in one transaction" pattern this project already uses everywhere else.
