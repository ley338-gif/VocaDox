# 0011 — Conversation/source-media separation and immutable-source integrity

## Status
Accepted

## Context
Phase 2 introduces the first real "evidence source" data: recorded/uploaded
conversation audio. Everything VocaDox will later derive (transcripts,
diarization, extracted facts, generated documents — Phase 3+) must be
traceable back to an unmodified original, per the evidence-first data model
(ADR-0004) and `docs/architecture/domain-model.md`'s Source → Facts →
Document provenance chain.

## Decision
Three separate concepts, three separate tables:

- **`Conversation`** — the logical unit (title, type, status, org,
  privacy/retention pointers). Never holds bytes.
- **`MediaAsset`** — one row per physical audio object, `kind` ∈
  `{SOURCE_AUDIO, NORMALIZED_AUDIO, ATTACHMENT}`. A `SOURCE_AUDIO` row is
  the original, immutable capture; a `NORMALIZED_AUDIO` row (Phase 2 uses
  `NoOpMediaNormalizer`, see ADR-0014) is always a *new* row with
  `derived_from_media_id` pointing back at the source — never an in-place
  rewrite of the source row's `storage_key` or bytes.
- **(future) Transcript / Evidence** — not implemented in Phase 2; will
  reference `MediaAsset` the same way.

Every ingested `MediaAsset` gets a SHA-256 computed while the bytes are
first spooled to a controlled temp file (`app.media.service.spool_upload`),
persisted in `media_assets.sha256`, and never recomputed against
possibly-mutated storage — the hash is a property of the *ingestion event*,
which is exactly what "original captured/uploaded media is evidence source
material" requires. `docs/security/media-security.md` documents the
before/after/restart SHA-256 verification performed for the Phase 2
validation report.

Deletion (see ADR "soft-delete vs physical destruction" section of
`docs/architecture/conversations.md`) destroys the physical bytes of every
`MediaAsset` belonging to a soft-deleted `Conversation` — immutability
means "never silently altered while it exists," not "impossible to ever
delete."

## Alternatives considered
- **One `Conversation` row holding a single `storage_key`.** Rejected:
  can't represent "original + normalized" as distinct, independently
  retained objects, which the retention model (`RetentionPolicy.
  delete_source_media` vs `delete_derived_media`) explicitly needs to
  differentiate.
- **Overwriting the source row in place during normalization.** Rejected
  outright — this is the one thing the brief calls a hard "never." A
  `MediaAsset` row, once created, only ever has `deleted_at` written to it
  after creation; every other column is set once at ingestion.

## Consequences
- Every media-referencing query must filter `deleted_at IS NULL`
  explicitly (see `app.conversations.authz.get_conversation_or_404` and
  the media list/get endpoints) — there is no soft-delete-aware default
  scope at the ORM layer yet. Documented, not hidden.
- Storage usage roughly doubles once real normalization exists (Phase 3+),
  since a derived asset never replaces its source. Accepted: this is the
  entire point of the immutability requirement.
