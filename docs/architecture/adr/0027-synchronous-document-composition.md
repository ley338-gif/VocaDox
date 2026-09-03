# 0027 — Document composition runs synchronously, not via ProcessingJob

## Status
Accepted

## Context
Every Phase 3/4 pipeline stage (NORMALIZE/TRANSCRIBE/DIARIZE/ALIGN/EXTRACT)
is a `ProcessingJob` dequeued and executed by a dedicated worker process —
`app.processing.models.ProcessingJob`'s docstring states this as a hard
rule: "Never executed inline in an HTTP request handler." That rule exists
because each of those stages calls a slow, blocking external provider
(ffmpeg, an ASR model, a diarization model, an LLM) that would otherwise
tie up an API request worker for seconds-to-minutes and risk request
timeouts.

Phase 5's document composition (`app.documents.service.compose_document`)
is different in kind: it calls no provider at all. It reads already-
persisted `ExtractedFact` rows for one conversation (typically tens, not
thousands) and deterministically renders them into sections/statements —
a pure, sub-millisecond, CPU-only transformation with no I/O beyond the
database queries the request handler was already going to need to check
authorization/load the conversation.

## Decision
`POST /conversations/{id}/document/compose` calls `compose_document`
directly inside the request handler and returns `200` with the composed
`DocumentResponse` immediately — no `ProcessingJob`/`ProcessingRun`-via-
worker round trip, no `202 Accepted` + poll pattern. It still:

- Requires an explicit trigger (never automatic), matching spec's
  "explicit trigger, not automatic" principle used for every other stage.
- Records a `ProcessingRun(run_type=COMPOSITION)` row for the same
  provenance guarantee every other stage gets (provider="vocadox-
  composition", model="deterministic-template-v1" — honest labels, not a
  disguised absence of a real model).
- Records `document.created`/`document.composed` audit events exactly
  like every other stage records its own completion event.

## Consequences
- Simpler frontend: the Document tab can call compose and immediately
  render the result, no polling loop needed (unlike the Facts tab, which
  must poll `GET .../facts` after `POST .../process/extract` returns
  `202`).
- If a future phase's composition becomes non-deterministic or provider-
  backed (e.g. an LLM-assisted narrative layer — not planned, and would
  contradict spec §23's rejected "Transcript -> 'write a report'"
  architecture), it would need to move to the ProcessingJob pattern at
  that point; this decision is scoped specifically to Phase 5's
  deterministic, fact-only composition and is not a precedent for
  skipping the job queue more broadly.
- `RunType.COMPOSITION` is a new enum value on the existing
  `app.processing.models.ProcessingRun` table (no new `JobType`, no new
  worker service, no new Compose container) — the smallest schema change
  that still gives composition the same provenance record every other
  stage has.
