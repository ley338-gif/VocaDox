# Intelligence pipeline (Phase 4)

## Pipeline shape (spec §23/§24)

```
Transcript -> Structured Facts -> Evidence Mapping -> Schema Validation
           -> Consistency Checks -> Contradictions -> Review Issues
```

Never `Transcript -> "write a report" -> Document`. Implemented in
`app.intelligence.service.run_extraction`, invoked only by the async
worker (`app.processing.orchestrator.execute_extract`) — never inline in
an HTTP request handler, exactly like Phase 3's speech/diarization/align
stages.

## Trigger and job lifecycle

1. A user with `fact:extract` permission calls
   `POST /api/v1/conversations/{id}/process/extract`. Explicit only — never
   automatic once a transcript reaches `READY` (spec: "explicit trigger,
   not automatic").
2. `app.processing.orchestrator.start_extraction` requires an active,
   `READY` `Transcript` to exist (409 if not), creates a `ProcessingJob`
   (`job_type=EXTRACT`) via the existing outbox/queue machinery
   (unchanged from Phase 3.1 — reused, not reinvented), and transitions
   the conversation `READY -> EXTRACTING`.
3. `worker-extraction` dequeues the job, runs `execute_extract`, which
   creates a `ProcessingRun(run_type=EXTRACTION)` for provenance, calls
   `run_extraction`, and on success transitions the conversation back to
   `READY`. A failure transitions to `FAILED` (never marks the underlying
   Transcript as failed — see `app.workers.processing_worker
   ._mark_transcript_and_conversation_failed`'s Phase 4 special case,
   since the transcript itself is unaffected by an extraction failure).

## Extraction categories

See `docs/architecture/adr/0025-extraction-schema-design.md` for the full
rationale. Three categories today: `general_fact` (subject/attribute/value
triples), `decision`, `task` (covers both "Tasks" and "Follow-Ups").
Each is requested as an independent LLM call with its own Pydantic schema
(`app.intelligence.schemas`) — never one shared prompt.

## Model configuration

The extraction model is a `model_profiles` row
(`app.profiles.ModelProfile`, purpose=`extraction`), not a hardcoded
string — `app.profiles.service.get_active_profile` is the only place
worker code learns which model/temperature/max_tokens to use. This is a
deliberately minimal foundation, NOT the full Phase 6 Processing Profiles
system (no Speech/Diarization/Document-Model/Template/Prompt-Version/
Language/Retention-Policy bundling into named presets) — see
`docs/architecture/future-considerations.md`.

## Uncertainty (spec §25)

`app.intelligence.uncertainty.classify` derives real signals from actual
extraction output and transcript state — never decoration:

| Category | Derived from |
|---|---|
| `MISSING_EVIDENCE` | No claimed segment sequence resolved to a real transcript segment |
| `AMBIGUOUS_TERM` | The model's own `certainty=unclear` |
| `INCOMPLETE_VALUE` | `certainty=incomplete`, or any field value is the literal `NOT_MENTIONED` |
| `LOW_TRANSCRIPTION_CONFIDENCE` | Average ASR confidence of the linked segment(s) below threshold (reuses Phase 3's stored per-segment `confidence`) |
| `MISSING_CONTEXT` | Evidence resolved, but the linked segment's text is too short to independently confirm a `stated`-certainty fact |
| `USER_REVIEW_REQUIRED` | Rolled up whenever any HIGH/CRITICAL signal above fires |

Each maps to a `ReviewIssueSeverity` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`).
See PHASE_4_VALIDATION_REPORT.md for real-model evidence that
`NOT_MENTIONED` (never a fabricated value) is genuinely produced by the
model when information is absent.

## Contradiction detection (spec §26)

See `docs/architecture/adr/0026-contradiction-detection.md`. A structural
rule, not an LLM judgment call: same-conversation `general_fact` items
with the same normalized `(subject, attribute)` and a different `value`
produce a `ReviewIssue(issue_type=POTENTIAL_CONTRADICTION)` referencing
both facts. Neither fact is auto-resolved.

## Review issues (spec roadmap)

`review_issues` (`app.review.models.ReviewIssue`) is a minimal, read-only
surface for Phase 4 — `GET /conversations/{id}/review-issues`. **NOT**
Phase 5's Review Wizard: no approval gating, no correction workflow, no
"N found / M reviewed" progress UI. `ReviewIssueStatus` only has `OPEN`/
`ACKNOWLEDGED` today; resolution semantics are deferred.

## Deferred to Phase 5/6

Document generation/composition, document revisions, approval workflow,
templates/template versions, prompt version lifecycle, the full
Processing Profiles system, the Review Wizard UX, export,
analytics/evaluation. See `docs/architecture/future-considerations.md`.
