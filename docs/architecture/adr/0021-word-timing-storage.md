# 0021 — Word-level timing storage: JSON column, not a row-per-word table

## Status
Accepted

## Context
`faster-whisper` produces per-word timestamps/confidence within each ASR
segment, and the alignment algorithm (ADR-0022) needs them to split
segments at speaker changes. The brief explicitly asks for a documented
decision either way: "Word-level storage only if it provides clear
Evidence/review value — a validated JSON word-timing field per segment
may be appropriate instead of millions of rows."

## Decision
`TranscriptSegment.words` is a single `JSON` column: a list of
`{text, start_ms, end_ms, confidence}` objects, scoped to that segment.
No separate `transcript_words` table.

Reasoning:
- Row-count math: a typical conversation transcript has tens to low
  hundreds of segments after alignment-driven splitting; word-level rows
  would multiply that by 5-10x (average words per segment) for the same
  information, with no query VocaDox currently needs run against
  individual words across segments (no "find all instances of word X
  across the whole corpus" feature exists or is planned in Phase 3/4).
- The only consumers of word-level timing in this phase are: (a) the
  alignment algorithm itself (operates on the in-memory
  `TranscriptionResult`, not the persisted rows, so it doesn't care about
  storage shape), and (b) future fine-grained transcript-highlighting UX
  (Evidence/review), which only ever needs "give me this segment's word
  list," never a cross-segment word query — a JSON blob read alongside
  the segment row it belongs to is strictly simpler and faster for that
  access pattern than a join.
- `words` is nullable — a provider/model without word timestamps (or the
  segment-level alignment fallback, ADR-0022) simply omits it; no
  placeholder rows, no fabricated timing.

## Consequences
- If a future phase needs true word-level querying (e.g. searching for
  a specific spoken word across an entire transcript corpus with its
  precise timestamp), this decision would need revisiting — documented
  here as the trigger condition for that future ADR, not treated as
  inconceivable.
- Postgres's native `JSON`/`JSONB` support makes this cheap to store and
  read; SQLAlchemy's portable `JSON` type (already used elsewhere in this
  codebase, e.g. `AuditEvent.event_metadata`,
  `ProcessingRun.configuration_snapshot`) is reused rather than
  introducing a new pattern.
