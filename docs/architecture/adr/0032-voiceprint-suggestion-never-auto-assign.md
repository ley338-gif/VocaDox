# 0032 — Voiceprint matching is suggestion-only; storage and threshold choices

## Status
Accepted (2026-09-07). Post-GA, roadmap item P1-2.

## Context

`alembic/versions/0013_known_speakers.py` deliberately deferred automatic
voice matching when it introduced `KnownSpeaker`: pyannote's diarization
pipeline already computes a per-speaker embedding internally (until now
discarded), but Phase 12 Finding #12 established that genuine multi-voice
diarization accuracy has never been independently verified against real
distinct voices — only same-voice-different-playback-rate fixtures. That
finding hasn't changed. The roadmap (P1-2) asks for automatic suggestion
of recurring speakers "with confidence, never silent assignment" — the
same constraint the 2026 migration already anticipated, now given an
actual mechanism.

Three implementation questions had to be settled: (1) where the
voiceprint lives and how repeated enrollments combine, (2) how a
candidate match is scored and gated, and (3) how a suggestion becomes a
real assignment.

## Decision

**1. One running-average embedding per `KnownSpeaker`, written only by
an explicit human enrollment action.** `known_speakers.voiceprint_embedding`
starts `NULL`; each enrollment (`app.people.service.enroll_voiceprint`)
folds one more detected speaker's embedding in via a simple weighted
mean (`voiceprint_sample_count` tracks how many). No enrollment ever
happens as a side effect of diarization, extraction, or accepting a
suggestion — only the dedicated enroll endpoint
(`POST .../speakers/{id}/enroll`) writes it, and it always requires the
caller to say explicitly which person this voice is.

**2. Matching is a plain cosine-similarity comparison, pure Python, no
new dependency.** `app.people.matching.cosine_similarity`/
`find_best_match` operate on the JSON-stored float lists directly —
pgvector or a vector index were considered and rejected for the same
reason ADR-0030 rejected pgvector for P0-1: this compares at most a
handful of embeddings per diarization run against one organization's
enrolled voiceprints, not a large-scale similarity search, so a real
vector index would add operational weight (an extension, index
maintenance) for no measurable benefit at this scale.

**3. A 0.75 cosine-similarity threshold gates whether a suggestion is
recorded at all.** Chosen conservatively per the same finding that
justified deferring this feature in the first place: a missed suggestion
costs one extra manual click; a wrong one risks attaching the wrong
person's name to what was actually said. Below threshold,
`suggested_known_speaker_id`/`suggested_confidence` are left `NULL`
(re-diarizing clears a stale suggestion the same way) rather than
surfacing a low-confidence guess dressed up as a percentage.

**4. Accepting a suggestion runs through the exact same `assign_speaker`
code path a manual assignment uses.** `app.diarization.service.
accept_suggestion` only resolves *which* participant to assign (reusing
one already linked to the suggested KnownSpeaker on this conversation, or
creating one) — the assignment itself, its audit event
(`speaker.suggestion_accepted`), and its permission gate (`speaker:assign`,
identical to a manual PATCH) are unchanged. A suggestion is data attached
to a `DetectedSpeaker` row; it is never a second, parallel assignment
mechanism.

## Consequences

- No new runtime dependency, no new network call (ADR-0007).
- Enrollment requires `known-speaker:manage` in addition to
  `speaker:assign` (the enroll endpoint checks both) because it mutates
  an organization-wide `KnownSpeaker`, not just this conversation —
  mirrors the frontend's existing two-permission gate on "remember as
  known person".
- If a future diarization model changes embedding dimensionality,
  `enroll_voiceprint` raises `VoiceprintDimensionMismatchError` (surfaced
  as 409) rather than silently averaging incompatible vectors — an
  admin would need to re-enroll from scratch with the new model. Not
  automated, since detecting "the model changed" reliably from inside
  this function isn't possible without also tracking model provenance,
  which this feature doesn't otherwise need.
- Should real deployment ever show the 0.75 threshold is miscalibrated
  (too many missed or wrong suggestions), it is a single named constant
  (`app.people.matching.DEFAULT_SUGGESTION_THRESHOLD`) — a full
  precision/recall evaluation of it would need real distinct voices,
  which is exactly the unverified pipeline this ADR's context section
  describes, so it is deliberately not claimed as calibrated today.
