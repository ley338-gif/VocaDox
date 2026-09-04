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

## Model configuration and template-driven categories (Phase 6)

The extraction model is a `model_profiles` row (`app.profiles.ModelProfile`,
purpose=`extraction`), not a hardcoded string. As of Phase 6 it is a real,
versioned, admin-manageable entity (`app.profiles.service
.update_model_profile` snapshots a `ModelProfileVersion` before every
edit), and which categories get extracted is itself template-driven
(`app.templates.schema_builder`) rather than the fixed 3-category dict
Phase 4 hardcoded — see `docs/architecture/templates.md` for the full
Template Engine / Processing Profile / Configuration Hierarchy
architecture. `app.profiles.resolver.resolve_effective_config` (SYSTEM
DEFAULT -> PROCESSING PROFILE -> CONVERSATION OVERRIDE) is the one place
`app.processing.orchestrator.execute_extract` learns which
model/template/prompt version actually applies to a given conversation.

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

## Review issues (Phase 4 read surface + Phase 5 Review Wizard)

`review_issues` (`app.review.models.ReviewIssue`) — Phase 4 added the
read-only `GET /conversations/{id}/review-issues` surface; Phase 5 added
real resolution via `PATCH /conversations/{id}/review-issues/{issue_id}`
(confirm/correct/remove one targeted fact, closing the issue) and
approval gating (an unresolved `HIGH`/`CRITICAL` issue blocks a document
from `APPROVED`). See `docs/architecture/documents.md` for the full
Review Wizard / approval workflow.

## Status as of Phase 6

Document generation/composition, document revisions, the Review Wizard
UX, and export are implemented (Phase 5) — see
`docs/architecture/documents.md`. The Template Engine, prompt version
lifecycle, and the full Processing Profiles/Configuration Hierarchy system
are implemented (Phase 6) — see `docs/architecture/templates.md`. Still
deferred: analytics/evaluation (Phase 8), and the items listed under
"Phase 6 additions" in `docs/architecture/future-considerations.md`.
