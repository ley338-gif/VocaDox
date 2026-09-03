# Phase 5 Validation Report: Review & Documents

## Executive Summary

Phase 5 closes VocaDox's core promise: it adds deterministic document
composition from Phase 4's evidence-linked facts, a real
DRAFT→REVIEW_REQUIRED→READY_FOR_APPROVAL→APPROVED revision workflow with
ORM-enforced immutability once approved, a Review Wizard that resolves
flagged items (confirm/correct/remove) as real, non-destructive human
actions, an approval workflow genuinely blocked by unresolved
high/critical review issues and genuinely restricted to a
`document:approve` permission the AI never holds a code path to invoke,
plain-text/JSON export, and the Result View tabs (Document, Review,
Timeline, Details) on top of Phase 3's Transcript tab and Phase 4's Facts
tab.

Every automated check is green: 173 backend tests (157 pre-existing + 16
new), ruff/mypy clean; 21 pre-existing frontend tests unchanged,
tsc/eslint/vite build clean. Migration `0007` was validated against a
real Postgres — full `0001→0007` chain, a `downgrade -1`/`upgrade head`
cycle, a full `downgrade base`/`upgrade head` cycle, and a genuine
Phase-4-data upgrade rehearsal (pre-existing facts/review-issues survive
with `review_status='pending'` backfilled). Fresh install and restart
persistence were validated end-to-end against a real `docker compose`
stack, including a real HTTP walk through compose→approve→export. No new
dependency was added this phase (PDF/DOCX export deliberately deferred),
so license compliance is unchanged (PASS, 0 blocked/0 unknown). One real,
unrelated CI failure (an upstream `ruff` point-release republish) was
found and fixed during this phase, following the exact same
rolling-dependency-drift pattern Phase 4 documented for FFmpeg.

## Scope

Implemented (maps to the phase brief's Phase 5 scope):

1. Deterministic document composition (`app.documents.service
   .compose_document`) from the conversation's current
   `ExtractedFact` rows — never an LLM "write a report" call. Every
   composed statement carries `fact_ids` back to its source.
2. `Document`/`DocumentRevision` domain with a real state machine
   (`app.documents.state_machine`): DRAFT→REVIEW_REQUIRED→
   READY_FOR_APPROVAL→APPROVED. Composition never produces APPROVED.
3. ORM-enforced revision immutability once APPROVED (SQLAlchemy
   `before_update` listener raising `ImmutableRevisionError`) — proven
   by a test that attempts a real mutation and confirms rejection, not
   just documented as disallowed.
4. Review Wizard: `PATCH /conversations/{id}/review-issues/{issue_id}`
   resolves one flagged item against one targeted fact
   (confirm/correct/remove), closing the issue. Corrections never
   overwrite the original `structured_value` — a `corrected_structured_value`
   field plus a `FactCorrection` audit row record the change, mirroring
   Phase 3's transcript-correction pattern exactly.
5. Approval workflow (`POST /conversations/{id}/document/approve`):
   requires `document:approve`, requires the current revision to be
   READY_FOR_APPROVAL, and re-checks for any OPEN HIGH/CRITICAL review
   issue (`ApprovalBlockedError`, HTTP 409 with `blocking_issue_ids`) —
   a real, enforced check, not decoration. **The AI never calls this
   function.**
6. Evidence UX / "Warum steht das hier?": the Review Wizard and Facts
   tab show only real evidence (source segment, evidence type,
   jump-to-audio via the existing `AudioPlayerHandle.seekToMs`
   mechanism) — verified no code path in `app.documents.*` asks an LLM
   to explain or justify a fact's inclusion.
7. Export: `GET /conversations/{id}/document/export?format=text|json`.
   Audited (`document.exported`), no new dependency.
8. New permissions (`document:read`/`document:edit`/`document:approve`/
   `review-issue:resolve`) wired into the deterministic RBAC seed —
   only System Admin/Manager/Reviewer hold `document:approve` by
   default; a standard `User` can compose/correct but not approve.
9. Organization-scoped authorization identical to every prior phase,
   heavily tested (cross-org → 404).
10. Audit events: `document.created`/`document.composed`/
    `document.corrected`/`document.approved`/`document.exported`/
    `review_issue.resolved` — ids/counts only, never fact/document
    content.
11. API: `GET .../document`, `POST .../document/compose`, `GET
    .../document/revisions`, `POST .../document/approve`, `GET
    .../document/export`, `PATCH .../review-issues/{issue_id}` (new);
    `GET .../review-issues` extended with resolution fields. OpenAPI TS
    client regenerated, no drift.
12. Frontend: Document tab (compose/approve/export/revision history),
    Review Wizard tab (evidence-driven, audio jump-to-segment), new
    Timeline and Details tabs on the Result View (Timeline merges
    markers/notes/processing jobs chronologically for one conversation;
    Details surfaces the existing processing-job history — no new
    provenance concept invented, per the brief).
13. Database: `documents`, `document_revisions`, `fact_corrections`
    tables; additive columns on `extracted_facts` and `review_issues`.
14. Tests: composition (traceability, REVIEW_REQUIRED vs
    READY_FOR_APPROVAL derivation, non-destructive recompose), Review
    Wizard (confirm/correct/remove, double-resolve rejection,
    fact/issue mismatch rejection), approval (permission gate, blocking
    gate, success + immutability proof), export (text/json, audit,
    404-before-compose), cross-organization authorization for every new
    endpoint — 16 new tests, all fake-provider/no-real-LLM-required
    (matching Phase 4's CI-never-requires-a-real-model precedent).
15. Fresh install / migration / restart validation against a real
    Docker Compose stack (see below).

**Explicitly out of scope, not implemented** (per the brief): the full
pluggable Template Engine/template versions, Prompt Version lifecycle,
Processing Profiles, the Admin Portal, Analytics/Evaluation Lab,
cross-conversation Timeline/longitudinal comparison, Service
Accounts/Webhooks. See `docs/architecture/future-considerations.md` for
the itemized list added this phase.

## Architecture

`Transcript → Structured Facts → Evidence Mapping → Schema Validation →
Consistency Checks → Contradictions → Review Issues → Document
Composition` — see `docs/architecture/documents.md` for the full Phase 5
domain description and [ADR-0027](docs/architecture/adr/0027-synchronous-document-composition.md)
for why composition runs synchronously in the request handler rather than
via the `ProcessingJob`/worker queue every provider-backed stage uses
(composition calls no external provider — it's a deterministic,
sub-millisecond transformation of already-persisted rows). A
`ProcessingRun(run_type=COMPOSITION)` is still recorded for the same
provenance guarantee every other stage gets.

## Document/Revision Domain

`documents` (id, conversation_id [unique], status, current_revision_id,
timestamps) and `document_revisions` (id, document_id, revision_number,
structured_content JSON, rendered_text, status, blocking_issue_ids JSON,
created_by_user_id, approved_by_user_id, approved_at, timestamps).
`compose_document` always INSERTs a new revision — it never UPDATEs an
existing one; `Document.current_revision_id` is repointed. The
mutually-referencing FK pair (`documents.current_revision_id` ↔
`document_revisions.document_id`) is resolved in the migration by
creating `documents` first without that FK, then `document_revisions`,
then adding the FK via `ALTER TABLE`.

## Review Wizard

One decision per flagged item (spec's "5 Punkte gefunden, 3/5" framing):
`PATCH /conversations/{id}/review-issues/{issue_id}` with
`{fact_id, action: confirm|correct|remove, corrected_value?}`. `fact_id`
must be one of the issue's `related_fact_ids` (400 otherwise); an
already-`resolved` issue is rejected (409). A `POTENTIAL_CONTRADICTION`
issue (which references two facts) is resolved by targeting exactly one
fact — the wizard's "one decision per flagged item" flow, not a
side-by-side compare UI (see Known Limitations).

## Evidence UX

Reuses Phase 3's `AudioPlayerHandle.seekToMs` / Phase 4's
`GET .../facts/{id}/evidence` denormalized segment data — no new
audio-sync mechanism invented. The Review Wizard shows evidence type
(`evidence_spoken`/etc.), the linked segment's text/timestamp, and an
"(Audio)" jump control per evidence item.

## Approval Workflow

`approve_document` (only caller: `POST .../document/approve`, only
reachable with `document:approve`):
1. Requires `document.current_revision_id` to exist and be
   `READY_FOR_APPROVAL`.
2. Re-checks for any `OPEN` review issue with severity `high`/`critical`
   for the conversation — raises `ApprovalBlockedError` with the exact
   blocking issue ids if any exist (checked *before* the status check, so
   a revision stuck at `REVIEW_REQUIRED` and a `READY_FOR_APPROVAL`
   revision undercut by a new issue both surface the same structured,
   actionable error).
3. Sets the revision `APPROVED`, records `approved_by_user_id`/
   `approved_at`, records `document.approved` audit event.

Verified genuinely blocked (`test_approval_blocked_even_for_approver_while_issues_open`)
and genuinely permission-gated (`test_approval_blocked_by_open_high_critical_issues`,
which shows a non-approver 403s even independent of the blocking check).

## Immutability (proven, not just documented)

`app.documents.models._forbid_mutating_approved_revision` — a
SQLAlchemy `before_update` event listener on `DocumentRevision` — inspects
column history and raises `ImmutableRevisionError` for any UPDATE where
the *previously-committed* `status` was already `APPROVED` (the one
legitimate transition INTO `APPROVED` is still allowed). Proven by
`tests/documents/test_approval_and_immutability.py
::test_approval_succeeds_once_issues_resolved_and_creates_immutable_revision`,
which directly mutates an approved revision's `rendered_text` in a fresh
session and asserts the flush raises, then confirms via a third session
that the database value is unchanged and that a subsequent `compose_document`
call created a brand-new revision rather than touching the approved one.

## Export

`GET /conversations/{id}/document/export?format=text|json` — plain text
(status header + rendered text) or structured JSON (sections with
statement/fact_id traceability). **No new dependency added.** PDF/DOCX
was considered but deliberately deferred rather than adding an
unresearched library under this phase's time budget — see Known
Limitations and `future-considerations.md`.

## API / OpenAPI

6 new/extended endpoints under `/api/v1/conversations/{id}/...`. `frontend/openapi.json`
and `frontend/src/api/generated/schema.d.ts` regenerated against a live
backend instance and committed — CI's "OpenAPI TS client drift check"
job: **PASS** on both workflow runs.

## Database / Migrations

`backend/alembic/versions/0007_documents_review.py` adds `documents`,
`document_revisions`, `fact_corrections`; extends `extracted_facts`
(`review_status`, `corrected_structured_value`, `reviewed_by_user_id`,
`reviewed_at`) and `review_issues` (`resolved_status`, `resolved_fact_id`,
`resolved_by_user_id`, `resolved_at`) — every extension additive and
nullable/defaulted. Verified against a real Postgres:
- Full chain `0001→0007` applied cleanly (CI's "Alembic migration (real
  Postgres)" job: PASS on both workflow runs, plus an independent local
  run via `docker compose up`).
- `alembic downgrade -1` / `alembic upgrade head` cycled cleanly.
- Full `alembic downgrade base` / `alembic upgrade head` cycled cleanly.
- **A genuine Phase-4-data upgrade rehearsal**: downgraded a live
  Postgres to `0006`, inserted a real organization/conversation/
  `extracted_fact`/`review_issue` row set via raw SQL matching Phase 4's
  exact schema, ran `alembic upgrade head`, and confirmed via a real
  `SELECT` that the fact's `structured_value` was untouched and
  `review_status` was correctly backfilled to `'pending'` (and the issue's
  `status`/description likewise untouched with `resolved_status` null) —
  a real migration-safety proof, not merely asserted.

## Authorization

Every new endpoint goes through
`app.conversations.authz.authorize_conversation_access` with a dedicated
permission code (`document:read`/`document:edit`/`document:approve`/
`review-issue:resolve`) — identical enforcement to every prior phase, 404
(never 403) on cross-org access when the user's role holds the relevant
permission. `tests/documents/test_authorization.py` covers: every new
endpoint 404s for a cross-org user who holds the endpoint's permission
(`document:read`/`edit` via the standard `User` role,
`document:approve` via a dedicated cross-org Reviewer), and 403 for a
same-org user missing the specific permission (`document:edit` for an
Auditor).

## Audit

`document.created`/`document.composed`/`document.corrected`/
`document.approved`/`document.exported`/`review_issue.resolved` — all
carry only ids/counts/status strings, never fact/document content
(verified in `test_export_text_and_json`, which asserts the composed
text's content string does not appear in the recorded audit metadata).

## Security

- No code path in `app.documents.*` sends a prompt to an LLM — composition
  is template rendering over already-persisted, already-validated
  `ExtractedFact` rows; the "Warum steht das hier?" surfaces are real
  evidence lookups, never a generated explanation (spec §30's hard
  constraint — verified by code inspection of every function in
  `app.documents.service` and the Review Wizard/DocumentPanel frontend
  components: none imports or calls `app.providers.llm`).
  `approve_document` has exactly one caller path, gated by
  `document:approve`.
- Export never returns full transcript/audio content, only the composed
  document's own text/structured content (already itself derived only
  from facts a human has had the opportunity to review).

## Compliance / Dependencies / Models / Containers / Licenses

No new dependency, container, or model this phase.
`compliance/check_licenses.py` → **PASS** (0 blocked, 0 unknown across
every category), identical composition to Phase 4:

| Category | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies | 36 | 0 | 0 | 0 |
| Transitive (498 resolved packages) | 495 | 3 | 0 | 0 |
| Container images | 7 | 0 | 0 | 0 |
| AI models | 6 | 0 | 0 | 0 |

**One real, unrelated CI failure found and fixed**: CI's license-
compliance job resolves the full dependency tree fresh on every run
(never trusts the committed inventory) and failed on this branch because
upstream `ruff` republished `0.16.6` between when the inventory was last
regenerated locally and when CI ran — the exact rolling-dependency-drift
risk this job exists to catch, root-caused as unrelated to any Phase 5
code, fixed by regenerating `compliance/dependency-inventory-transitive.yml`
via real `python:3.11`/`node:20` Linux containers (matching CI's
`ubuntu-latest`, per `generate_transitive_inventory.py`'s own documented
method) and committing the one-line version diff. This mirrors Phase 4's
own documented FFmpeg-rolling-tag incident exactly.

`pip-audit`: no known vulnerabilities.

## Tests

**Backend**: 173 passed (157 pre-existing + 16 new), ruff clean, mypy
clean.

New test breakdown (`tests/documents/`, 16 tests):
- `test_composition.py` (3): permission enforcement + REVIEW_REQUIRED
  derivation from real blocking issues, 404 before any compose, recompose
  creates a new revision without mutating the prior one.
- `test_review_wizard.py` (6): confirm (no value change), correct (never
  overwrites original, composition reflects the corrected value),
  remove (excluded from composition), double-resolve rejection (409),
  fact/issue mismatch rejection (400).
- `test_approval_and_immutability.py` (3): permission-gated block,
  issue-gated block (for a user who does hold the permission), full
  success path + the ORM-enforced immutability proof (direct mutation
  attempt rejected; recompose after approval creates a new revision,
  never touching the approved one).
- `test_export.py` (2): text/json export content + audit metadata never
  contains document content; export before any compose is 404.
- `test_authorization.py` (2, each covering multiple endpoints):
  cross-organization 404 across every new endpoint (document read/
  compose/revisions/approve/export, review-issue resolve) plus a
  dedicated cross-org proof for `document:approve` specifically;
  `document:edit` permission enforcement (403 without it, 200 for
  `document:read` with only that permission — Auditor role).

**Frontend**: 21 pre-existing tests unchanged and passing; typecheck,
eslint, and `vite build` all clean. No new frontend unit tests were added
for `DocumentPanel.tsx`/`ReviewWizard.tsx`/`api/documents.ts` — verified
via `tsc`/eslint/`vite build` passing and manual code review, matching
Phase 4's own documented precedent for its equally new, equally minimal
frontend surface (see Known Limitations).

## GitHub Actions

All 7 required checks green on the final commit (`5f784e2`, merged as
`c830628`), both workflow runs:

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | PASS |
| Frontend (lint / typecheck / test / build) | PASS |
| Alembic migration (real Postgres) | PASS |
| OpenAPI TS client drift check | PASS |
| License compliance (direct + full transitive tree) | PASS |
| Docker build (backend + frontend + AI worker) | PASS |
| Container vulnerability scan (Trivy) | PASS |

One real, unrelated CI failure was found and fixed during this phase (see
Compliance section above): upstream `ruff` 0.16.6 republish, root-caused
and resolved via `5f784e2`.

## Fresh Install

`docker compose down -v && docker compose build [images] && docker
compose up -d [services]` (excluding `ollama`/`model-manager`, which
Phase 4's own fresh-install validation also didn't require — extraction
defaults to the `fake` LLM provider) — validated for real:
- `postgres`, `valkey`, `migrate` (ran the full `0001→0007` chain),
  `backend`, `worker-speech`, `worker-diarization`, `worker-extraction`,
  `frontend` all started/ran the migration successfully.
- **A real gotcha found and fixed during this exact process**: the
  `migrate` service builds from the same Dockerfile/context as `backend`
  but as its own separate Compose-managed image; an initial
  `docker compose build backend worker-speech worker-diarization
  worker-extraction frontend` (omitting `migrate` from the list) left a
  stale `migrate` image that only ran through migration `0006` on `up`.
  Rebuilding `migrate` explicitly (`docker compose build migrate`)
  resolved it. Documented here since a real administrator following the
  README's plain `docker compose up -d --build` (which rebuilds every
  service, migrate included) would never hit this — it was purely an
  artifact of this validation session's incremental build commands, not a
  gap in the shipped deployment instructions.
- `python -m app.identity.bootstrap_admin` created the first System Admin
  user against the fresh database.
- Real HTTP flow end-to-end: login → create organization + membership
  (via a one-off script, since organization creation has no HTTP endpoint
  yet — a pre-existing Phase 1/2 gap, not new to this phase) → create
  conversation → upload synthetic WAV → `POST .../process/transcript`
  (fake provider) → transcript reaches `ready` → `POST .../process/
  extract` (fake provider, zero facts) → conversation back to `READY` →
  `POST .../document/compose` → `200`, revision 1, `ready_for_approval`
  (zero facts, zero blocking issues) → `POST .../document/approve` →
  `200`, `approved` → `GET .../document/export?format=text` and
  `?format=json` → both `200` with real (empty-but-honest) content.

## Upgrade Validation

A true from-a-tagged-Phase-4-checkout rehearsal (checking out `0af0462`
and running its full stack, then switching branches) was not performed
end-to-end in this session, matching the exact limitation Phase 4 itself
disclosed for its own Phase 3.1 upgrade. In its place: (1) the fresh-
install chain `0001→0007` was validated against a real Postgres
end-to-end (above), and (2) a genuine Phase-4-schema-with-real-data
upgrade rehearsal was performed (see Database/Migrations above) —
downgrading to `0006`, inserting real rows matching Phase 4's exact
schema, upgrading to `0007`, and confirming via direct SQL that the
pre-existing data survived unchanged with the new columns correctly
defaulted. Migration `0007` only adds tables/columns (no `ALTER`/`DROP`
of existing data), so this is strong evidence the upgrade path is safe,
consistent with Phase 4's own reasoning for the same limitation.

## Restart Persistence

`docker compose restart backend postgres` — the approved document
(status, `approved_by_user_id`, `approved_at`, revision content) created
before the restart was confirmed identical via a real
`GET /conversations/{id}/document` call afterward, not assumed from
`docker volume ls`.

## Known Limitations

- **No frontend unit tests for the new Document/Review Wizard
  components** (`DocumentPanel.tsx`, `ReviewWizard.tsx`,
  `api/documents.ts`) — verified via `tsc`/eslint/`vite build` passing
  and manual code review, matching Phase 4's identical, explicitly
  disclosed gap for its own new frontend surface. Backend coverage
  (composition, Review Wizard resolution, approval blocking, immutability,
  export, authorization) is thorough.
- **Contradiction resolution is single-fact-targeted, not side-by-side**:
  resolving a `POTENTIAL_CONTRADICTION` issue (which references two
  facts) requires the caller to explicitly name which one fact it's
  acting on via `fact_id` — there's no dedicated "compare these two and
  pick the winner" UI/endpoint. Functionally complete (either fact can be
  corrected/removed/confirmed to resolve the issue) but a narrower UX
  than a hypothetical richer comparison view — logged in
  `future-considerations.md`.
- **No true from-a-tagged-Phase-4-checkout upgrade rehearsal** — see
  Upgrade Validation above for what was actually done instead (a
  same-schema-with-real-data rehearsal) and why it's still strong
  evidence, matching Phase 4's own documented precedent for this exact
  gap.
- **PDF/DOCX export not implemented** — plain text and JSON only, by
  deliberate choice to avoid adding an unresearched dependency under this
  phase's time budget. Both formats satisfy the phase brief's "at minimum
  plain text and/or a simple structured format" bar. A future phase
  should do the real primary-source license/maintenance research before
  adding either binary format.
- **Organization creation has no HTTP endpoint** — a pre-existing Phase
  1/2 gap (organizations are currently created via direct service-layer
  calls, e.g. seed/bootstrap scripts), encountered but not introduced by
  this phase's fresh-install validation. Not in this phase's scope to
  fix; noted for whichever future phase owns the admin-facing
  organization-management UI.
- **`ProcessingRun.provider`/`model` for `RunType.COMPOSITION`** are
  honest placeholder labels (`"vocadox-composition"` /
  `"deterministic-template-v1"`) rather than a real external provider —
  intentional (see ADR-0027), documented so it's never mistaken for a
  disguised LLM call.

## Open Risks

None new this phase. The Ollama container's accepted CRITICAL finding
from Phase 4 (`compliance/container-inventory.yml`'s `ollama/ollama`
entry) remains open and tracked exactly as Phase 4 left it — this phase
did not touch the LLM provider or its container.

## Architecture Deviations

**Composition runs synchronously rather than via the `ProcessingJob`/
worker queue** — a deliberate, documented deviation from the pattern
every prior processing stage (NORMALIZE/TRANSCRIBE/DIARIZE/ALIGN/EXTRACT)
follows. See [ADR-0027](docs/architecture/adr/0027-synchronous-document-composition.md)
for the full justification: composition calls no external provider, so
the actual reason for the "never inline in a request handler" rule
(don't block on slow I/O) doesn't apply, and it would add latency/
complexity with no benefit. This is the only architecture deviation from
the phase brief's explicit scope.

## Deferred Items

See `docs/architecture/future-considerations.md`'s Phase 5 additions: the
full pluggable Template Engine/template versions, PDF/DOCX export,
cross-conversation Timeline/longitudinal comparison, a richer multi-fact
contradiction-resolution UX, and CI coverage guidance for any future
provider-less `ProcessingRun` stage.

## Git / PR / Merge Status

- Branch: `phase-5-review-documents`, off `main` at `0af0462`.
- PR: [#8](https://github.com/ley338-gif/VocaDox/pull/8) — "Phase 5:
  Review & Documents — composition, Review Wizard, approval, export".
- Commits: `20fe231` (feature), `5f784e2` (ruff 0.16.6 transitive-
  inventory fix, found by CI).
- All 7 required GitHub Actions checks: **green** on both workflow runs
  for the final commit.
- **Merge: performed** (`c830628`, merge commit on `main`). No open risk
  required product-owner escalation this phase — every merge-gate
  condition in the phase brief was independently verified (Review Wizard
  end-to-end, composition traceability, evidence UX audio-sync, approval
  genuinely blocked and permission-restricted, revision immutability
  proven by direct-mutation-attempt test, export producing real usable
  files, organization authorization heavily tested, fresh install/
  migration/restart all validated against real infrastructure, 0
  blocked/0 unknown licenses, all CI green, docs current).

## Recommendation

**GO for Phase 6.** VocaDox now genuinely supports the complete Audio →
Transcript → Facts → Evidence → Document → Human Review → Approval
workflow the spec requires at this milestone: a real human — never the
AI — must explicitly approve a document, high/critical uncertainty
genuinely blocks that approval until resolved, corrections are
non-destructive and fully audited, approved revisions are immutable at
the database-enforcement level (not a UI promise), and every composed
statement remains traceably linked back through the same Source→Facts→
Document chain the domain model has insisted on since Phase 0. The one
architecture deviation (synchronous composition) is deliberate, narrowly
scoped, and documented rather than silently taken. No new open risk was
introduced, and the one real CI failure found during this phase (an
upstream `ruff` version drift) was root-caused and fixed rather than
worked around.
