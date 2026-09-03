# Document composition, revisions, review, and approval (Phase 5)

## Pipeline shape (spec §23, completed)

```
Transcript -> Structured Facts -> Evidence Mapping -> Schema Validation
-> Consistency Checks -> Contradictions -> Review Issues
-> Document Composition
```

Phase 4 built everything up to "Review Issues". Phase 5 adds the final
step: `app.documents.service.compose_document` deterministically renders
the conversation's current facts (excluding any a human REMOVED,
preferring a CORRECTED value over the original) into a `DocumentRevision`
— never an LLM "write a report" call. Every statement in
`structured_content` carries the `fact_ids` it was rendered from.

## Workflow (spec §27)

```
DRAFT -> REVIEW_REQUIRED -> READY_FOR_APPROVAL -> APPROVED
```

Enforced by `app.documents.state_machine` (mirrors
`app.conversations.state_machine`'s pattern exactly). **The AI never sets
APPROVED** — `app.documents.service.approve_document` is the only caller
of that transition, and it's only reachable from
`POST /conversations/{id}/document/approve`, which requires a human user
holding the `document:approve` permission.

Composition decides `REVIEW_REQUIRED` vs `READY_FOR_APPROVAL` from a real
signal: whether any `review_issues` row for the conversation is `OPEN`
with `severity` `high`/`critical` (`app.documents.service
._open_blocking_issues`). Approval independently re-checks the same
condition and refuses (`ApprovalBlockedError`, HTTP 409 with
`blocking_issue_ids`) if any such issue is still open — this is the real,
enforced high/critical-blocks-approval rule from spec §27, not decoration.

## Why composition runs synchronously

See [ADR-0027](adr/0027-synchronous-document-composition.md). Unlike
NORMALIZE/TRANSCRIBE/DIARIZE/ALIGN/EXTRACT, composition calls no external
provider — it's a sub-millisecond, deterministic transformation of
already-persisted `ExtractedFact` rows — so it runs directly in the
`POST .../document/compose` request handler rather than through the
`ProcessingJob`/worker queue, while still recording a
`ProcessingRun(run_type=COMPOSITION)` for the same provenance guarantee
every other stage gets.

## Revisions are never destructively overwritten (spec §31)

`compose_document` always INSERTs a new `DocumentRevision` row — it never
updates an existing one. `Document.current_revision_id` is repointed to
the new row; older revisions remain queryable via
`GET /conversations/{id}/document/revisions`.

**An APPROVED revision is immutable, enforced by the ORM, not just "no
route calls update"**: `app.documents.models._forbid_mutating_approved_revision`
is a SQLAlchemy `before_update` listener on `DocumentRevision` that raises
`ImmutableRevisionError` for any UPDATE where the *previously committed*
status was already `APPROVED` (it allows exactly the one legitimate
transition INTO `APPROVED`). See
`tests/documents/test_approval_and_immutability.py
::test_approval_succeeds_once_issues_resolved_and_creates_immutable_revision`,
which attempts a real mutation on an approved revision directly against
the database and asserts it's rejected — not merely documented as
disallowed.

## Review Wizard (spec §28) and fact corrections

`PATCH /conversations/{id}/review-issues/{issue_id}` applies exactly one
decision — `confirm` / `correct` / `remove` — to one fact named in the
request body (`fact_id`, which must be one of the issue's
`related_fact_ids`), then marks the issue `RESOLVED`. This is a real human
action, not a cosmetic UI state:

- **confirm** (`ExtractedFact.review_status = CONFIRMED`): no value
  change, just a recorded reviewer + timestamp.
- **correct** (`review_status = CORRECTED`): the original
  `structured_value` is **never overwritten** — the correction is written
  to `corrected_structured_value`, and a `FactCorrection` row records
  previous/new value + who + when, mirroring
  `app.transcription.models.TranscriptSegmentCorrection`'s exact pattern
  from Phase 3. Composition prefers the corrected value when present (see
  `app.documents.service._effective_value`).
- **remove** (`review_status = REMOVED`): excluded from future
  compositions; the fact row and its evidence are never deleted.

A multi-fact `POTENTIAL_CONTRADICTION` issue is resolved by targeting
whichever one fact the reviewer acts on — matching the wizard's "one
decision per flagged item" flow (spec's illustrative "3/5" progress UI);
see Known Limitations in `PHASE_5_VALIDATION_REPORT.md` for the narrower
UX this implies vs. a hypothetical side-by-side contradiction-resolution
view.

## "Warum steht das hier?" (spec §30)

Never an LLM explanation. The Review Wizard and the Facts tab show the
same real evidence Phase 4 already exposes: `evidence_type`
(`EVIDENCE_SPOKEN`/etc.), the linked `TranscriptSegment`'s
speaker/timestamp/text, and a jump-to-audio control
(`AudioPlayerHandle.seekToMs`, the same mechanism Phase 3 built for
transcript playback). No code path in `app.documents.*` calls an LLM to
justify why a fact is included.

## Database

- `documents` (`app.documents.models.Document`): one row per
  conversation, `current_revision_id` FK.
- `document_revisions` (`DocumentRevision`): `structured_content`
  (sections/statements with `fact_ids`), `rendered_text`, `status`,
  `blocking_issue_ids` (denormalized snapshot — survives later issue
  resolution), `created_by_user_id`, `approved_by_user_id`/`approved_at`.
- `fact_corrections` (`app.intelligence.models.FactCorrection`):
  append-only correction audit trail.
- `extracted_facts` gained `review_status`/`corrected_structured_value`/
  `reviewed_by_user_id`/`reviewed_at` (additive, Phase 4 data survives
  unchanged with `review_status='pending'`).
- `review_issues` gained `resolved_status`/`resolved_fact_id`/
  `resolved_by_user_id`/`resolved_at` (additive) and a new `RESOLVED`
  `ReviewIssueStatus` value.

See `backend/alembic/versions/0007_documents_review.py`.

## Authorization

Same Permission + Organization Membership + Conversation's Organization
enforcement as every prior phase
(`app.conversations.authz.authorize_conversation_access`), with new
permission codes `document:read`/`document:edit`/`document:approve`/
`review-issue:resolve`. Only System Admin/Manager/Reviewer roles hold
`document:approve` by default (`app.identity.seed`) — a standard `User`
can compose/correct but not approve. See
`tests/documents/test_authorization.py`.

## Export

`GET /conversations/{id}/document/export?format=text|json` — plain text
or structured JSON of the current revision. PDF/DOCX deliberately
deferred (see `future-considerations.md`) rather than adding an
unresearched dependency. Audited (`document.exported`, ids/format only —
never full content).

## What's NOT built here

The full pluggable Template Engine, Prompt Version lifecycle, Processing
Profiles, cross-conversation Timeline, Admin Portal, Analytics — see
`future-considerations.md`.
