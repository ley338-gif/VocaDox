# Facts and evidence (Phase 4)

## What this is

Once a conversation's transcript is ready, you can ask VocaDox to extract
structured facts from it — decisions made, tasks/follow-ups, and general
facts (e.g. a medication and its dose, an appointment date). This is a
draft, machine-derived layer sitting on top of your real transcript: it
never replaces the transcript, and every fact links back to the exact
moment it came from. This is **not** the final document/report — that's a
later capability. Phase 4 stops at facts, their evidence, and honest flags
for anything uncertain or possibly contradictory.

## Triggering extraction

From a conversation whose transcript is `READY`:

```
POST /api/v1/conversations/{id}/process/extract
```

Requires the `fact:extract` permission. This runs in the background (like
transcription/diarization) — it is never triggered automatically. Poll:

```
GET /api/v1/conversations/{id}/facts
GET /api/v1/conversations/{id}/review-issues
```

## Reading a fact

```
GET /api/v1/conversations/{id}/facts/{fact_id}
GET /api/v1/conversations/{id}/facts/{fact_id}/evidence
```

Every fact has a `status`: `verified` (at least one transcript segment
was found to support it) or `unverified` (no segment could be linked —
still shown, never silently hidden). Every fact also has a `certainty`
from the extraction model itself: `stated`, `unclear`, `incomplete`, or
`not_mentioned` (used when a requested detail, like a due date, genuinely
wasn't said).

The `/evidence` endpoint returns the exact transcript segment(s) behind a
fact, including its timestamp — the frontend uses this to jump to and
highlight the exact spoken moment, the same way transcript playback
already works.

## Review issues

```
GET /api/v1/conversations/{id}/review-issues
```

Two kinds:
- **Uncertainty** — a fact's evidence is missing, its wording was
  ambiguous, a value wasn't stated, or the underlying transcription
  itself was low-confidence.
- **Potential contradiction** — two facts about the same subject/attribute
  (e.g. the same medication's dose) disagree. VocaDox never decides which
  one is correct — both are shown, flagged, for you to resolve.

This is a minimal, read-only list for Phase 4. A full review workflow
(marking issues resolved, correcting facts, approval before a document is
generated) is a later phase.

## What this is not

- Not a generated report or clinical document — see
  `docs/architecture/future-considerations.md` for what's deferred.
- Not automatic — extraction only runs when you ask for it.
- Not a substitute for the transcript — every fact traces back to it, and
  a fact with no traceable evidence is marked, never hidden or invented.
