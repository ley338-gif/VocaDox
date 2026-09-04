# Phase 9 Validation Report: Longitudinal Documentation

## Executive Summary

Phase 9 builds the master specification's roadmap §73 Phase 9 list —
Timeline, external reference grouping, conversation comparison, changes,
follow-ups, tasks — as a new `app.longitudinal` backend package built
directly on two entities that already existed before this phase: Phase 2's
`Conversation.external_reference` (the grouping key — no redundant field
added) and Phase 4's `extracted_facts` (the `task` category is the direct
source of AI-extracted Follow-ups/Tasks — no parallel fact type invented).

The comparison mechanism is a real, deterministic, structural comparison
over already-extracted `GENERAL_FACT` facts — never an LLM asked to
summarize "what changed," per the spec's explicit constraint ("Keine
unbelegte Interpretation von Aenderungen"). It reuses
`app.intelligence.contradictions.detect_contradictions` verbatim for
same-conversation contradictions and adds a new cross-conversation temporal
diff for `NEW`/`CHANGED`/`NOT_MENTIONED`. Every comparison result carries
the fact id(s) of both sides being compared.

**The phase's single most important test — cross-organization isolation
when two organizations coincidentally share the same `external_reference`
string — was verified twice**: with a dedicated automated test
(`tests/longitudinal/test_timeline_and_isolation.py::
test_cross_organization_same_reference_isolation`) and with a real, live
Docker Compose walkthrough (two real organizations, both using the
reference `"1"`, each with their own conversation): each organization's
timeline/comparison shows only its own data, and cross-organization access
via an explicit `organization_id` the caller isn't a member of is refused
with a real `403`, never a silently-empty or partial result. **Result:
PASS — no leak observed in either the automated test or the live check.**

247/247 backend tests pass (231 pre-existing + 16 new), ruff clean, mypy
clean (136 source files). 21 pre-existing frontend tests pass unchanged,
tsc/eslint/`vite build` clean. A real Docker Compose fresh install
(migration `0001→0010`), a real curl-driven walkthrough (timeline,
comparison, AI-extracted task sync from a real inserted fact, user-created
task lifecycle, non-permission-holder denial on every new endpoint, RBAC
reseed idempotency, and restart persistence) were all validated against a
real running Postgres/Valkey stack — not mocked. License compliance: PASS,
0 blocked/0 unknown — **no new dependency was added this phase** (verified
via `git diff main -- backend/pyproject.toml frontend/package.json`,
byte-identical). All 7 required GitHub Actions checks are green on the
final commit.

**One real, self-caught CI issue this phase** (see "Bugs Found and Fixed"):
the first-generated `frontend/openapi.json` was written via a
pretty-printed `json.dump(indent=2)` rather than the exact single-line
compact format FastAPI serves at `/openapi.json` — CI's drift-check job
compares byte-for-byte against a live-curled copy, so the first push failed
that check even though the schema content (and the generated TS client)
was correct. Fixed by regenerating from a locally-run `uvicorn` instance
(the same method the CI job itself uses) instead of calling
`app.openapi()` and dumping it manually.

## Scope

Implemented (maps to the phase brief's roadmap §73 list):

1. **Timeline & external-reference grouping** (`GET
   /conversations/{id}/related`, `GET /external-references/{ref}/
   timeline?organization_id=...`): every `Conversation` sharing
   `(organization_id, external_reference)`, oldest first, each with a
   genuinely useful summary (title, type, status, occurred-at, fact count)
   — no new grouping column, reuses Phase 2's `external_reference` exactly
   as instructed.
2. **Comparison** (`GET /external-references/{ref}/comparison?
   organization_id=...`): deterministic `NEW`/`CHANGED`/`NOT_MENTIONED`/
   `CONTRADICTED` classification over `GENERAL_FACT` facts across a
   Timeline's conversations. `CONTRADICTED` reuses
   `app.intelligence.contradictions.detect_contradictions` directly (a
   same-conversation contradiction on a `(subject, attribute)` pair);
   `NEW`/`CHANGED`/`NOT_MENTIONED` come from a new cross-conversation
   temporal diff (`app.longitudinal.comparison`). Every item carries the
   evidence fact id(s)/value(s) of both sides where both exist.
3. **Follow-ups / Tasks** (`app.longitudinal.models.FollowUpTask`, `GET/
   POST /conversations/{id}/tasks`, `PATCH /tasks/{id}`): a generic,
   domain-neutral action item with `source ∈ {AI_EXTRACTED, USER_CREATED}`
   and `status ∈ {OPEN, DONE, DISMISSED}`. `AI_EXTRACTED` rows are
   idempotently synced (matched by `source_fact_id`, never duplicated) from
   Phase 4's existing `extracted_facts(category="task")` rows on read;
   `USER_CREATED` rows are added directly through the API. No medical-
   specific task types are hardcoded (per the phase brief's explicit
   instruction).
4. **New migration** (`0010_longitudinal_documentation`): a single
   additive table, `follow_up_tasks` — Timeline and Comparison are pure
   read queries over existing Phase 2/4 tables, so no schema change was
   needed for either.
5. **New RBAC permissions**: `timeline:read`, `task:read`, `task:create`,
   `task:update` — granted to Manager (all four), Reviewer/Auditor
   (read-only plus `task:update`/none respectively — see table below),
   User (all four), matching each role's existing conversation-level
   access pattern.
6. **API** under `/api/v1`: `GET /conversations/{id}/related`, `GET
   /external-references/{ref}/timeline`, `GET /external-references/{ref}/
   comparison`, `GET/POST /conversations/{id}/tasks`, `PATCH /tasks/{id}`.
7. **Frontend**: two new tabs on `ConversationDetailPage` — "Related"
   (`LongitudinalPanel`: Timeline list + Comparison list, explicitly no
   LLM-narrative rendering) and "Tasks" (`TasksPanel`: AI-extracted vs.
   user-created badges, status update buttons, add-task form) — using the
   existing design system (`Badge`, `Button`, `TextInput`) consistently
   with every other tab.
8. **Audit**: `timeline.viewed`, `task.created`, `task.updated` — IDs/
   counts only (organization id, conversation count, task id, new status),
   matching Phase 7 Audit viewer's existing verbosity/pattern; never
   fact/task-description content in `event_metadata` (a deliberate
   editorial decision here: `task.created`/`task.updated` record only the
   task id and, for updates, the new status — not the description/
   assignee/due-date text — mirroring how `conversation.created` records
   only the conversation id, not its title).
9. **Tests**: 16 new backend tests
   (`backend/tests/longitudinal/`): 7 pure-function comparison-determinism
   tests (no DB), 5 API-level timeline/comparison tests (including the
   critical cross-org isolation test, for both Timeline and Comparison
   endpoints), 4 task-lifecycle/authorization tests.
10. **Documentation**: `docs/architecture/domain-model.md` ("Phase 9:
    Longitudinal Documentation" section), `docs/architecture/
    future-considerations.md` ("Phase 9 additions" — deferred items listed
    below), `docs/admin/README.md` (Phase 8→9 upgrade instructions).

**Explicitly out of scope, not implemented** (per the roadmap): Service
Accounts/API scopes/Webhooks (Phase 10), Backup/Restore/GPU-metrics
dashboard/automated Retention Cleanup (Phase 11), final hardening audit
(Phase 12), any notification/reminder/email system for tasks (none exists
anywhere in this codebase), any LLM-based "explain what changed" narrative
(the comparison is 100% deterministic — no LLM call is made anywhere in
`app.longitudinal`).

## Architecture

`app.longitudinal` is a new domain package: `models.py` (`FollowUpTask`,
the only genuinely new persisted state this phase — `FollowUpSource`/
`FollowUpStatus` enums), `comparison.py` (the pure, DB-free deterministic
comparison function — `compare_conversation_group`, unit-tested directly
with hand-built fact snapshots), `service.py` (the isolation-critical
compound-key queries — `get_timeline_conversations`, `build_comparison`,
task sync/CRUD), `api_schemas.py` (Pydantic request/response models),
`router.py` (the HTTP surface, following `app.conversations.authz`'s exact
Permission + Organization Membership pattern). Registered in
`app.core.app_factory` and `app.platform.db.model_registry` alongside every
other domain.

No new cross-cutting abstraction was needed (unlike Phase 8's
`get_llm_provider_for_model_identifier` factory) — this phase makes no LLM
calls and no new provider type, so `tests/test_architecture_boundaries.py`
required no changes and passes unmodified.

## Timeline & External Reference Grouping

`GET /external-references/{ref}/timeline?organization_id=...` (gated
`timeline:read`) and `GET /conversations/{id}/related` (gated via the
owning conversation's authorization, permission `timeline:read`). Verified:

- **Automated**: `test_timeline_groups_conversations_sharing_reference_
  within_one_org` creates 2 conversations sharing `external_reference=
  "CASE-100"` plus 1 decoy with a different reference in the same
  organization; asserts the timeline returns exactly the 2 matching
  conversations, chronologically. `test_related_conversations_endpoint_
  from_a_specific_conversation` and `test_related_conversations_with_no_
  external_reference_returns_self_only` cover the "reached from a specific
  conversation" entry point, including the no-reference-set case (returns
  the conversation itself only, not an error).
- **Live** (real Docker Compose, real Postgres): created two real
  organizations and two real users (one member of each), created a real
  conversation with `external_reference="1"` in each organization, and
  confirmed via curl that each organization's own timeline for `"1"` shows
  exactly its own conversation (see "Cross-Organization Isolation" below
  for the full transcript).

## Cross-Organization Isolation

**This is the phase's single most important guarantee.**
`Conversation.external_reference` is free text; two organizations can
coincidentally use identical reference strings (e.g. both numbering cases
"1", "2", "3", ...). `app.longitudinal.service.get_timeline_conversations`
and `build_comparison` both take an explicit `organization_id` and always
include it as a genuine SQL `WHERE` clause alongside `external_reference`
— never a broader query filtered down in Python afterward. The router
additionally verifies the caller is a member of the *requested*
`organization_id` (or `system:admin`) via `assert_organization_member_or_
admin` before running any query.

**Automated tests** (`tests/longitudinal/test_timeline_and_isolation.py`):

- `test_cross_organization_same_reference_isolation`: Alice (Org A) and
  Bob (Org B) both create a conversation with `external_reference="1"`.
  Bob's own-org timeline for `"1"` returns exactly 1 conversation (`"Org B
  Case 1"` — never Alice's `"Org A Case 1"`, never a count of 2). Bob's
  attempt to view Org A's timeline for `"1"` returns `403` (not 200 with
  empty data — a caller who is not a member of the requested organization
  is refused outright, so "no result" can never be confused with "there
  is genuinely no data here"). The symmetric check from Alice's side
  passes identically.
- `test_cross_organization_same_reference_isolation_in_comparison`: the
  identical guarantee, verified for the Comparison endpoint (not just
  Timeline) — Bob's own-org comparison for a shared reference `"7"`
  reports `conversation_count: 1`; his attempt against Org A is `403`.

**Live verification** (real Docker Compose, real Postgres, real HTTP,
session-cookie-authenticated — full transcript below):

```
== create Org B conversation, external_reference=1 (Bob) ==
{"id":"0117f870-...", "organization_id":"d1e58866-...", "external_reference":"1", ...}

== Bob views Org B timeline for '1' (own org) ==
{"external_reference":"1","conversations":[{"conversation_id":"0117f870-...","title":"Org B Case 1", ...}]}

== Bob attempts to view Org A timeline for '1' ==
HTTP_STATUS:403

== Alice views Org A timeline for '1' (own org) ==
{"external_reference":"1","conversations":[{"conversation_id":"c5012bb7-...","title":"Org A Case 1", ...}]}

== Alice attempts to view Org B timeline for '1' ==
HTTP_STATUS:403

== Bob views Org B comparison for '1' (own org) ==
{"external_reference":"1","conversation_count":1,"items":[]}
```

**Result: PASS.** No leak of Org A's data into Org B's view (or vice
versa) was observed in either the automated suite or the live check;
cross-organization access to an organization the caller isn't a member of
is refused with a genuine `403` in every case tested.

## Conversation Comparison Algorithm

`app.longitudinal.comparison.compare_conversation_group` is a pure
function (no DB access) over a list of `ConversationFactSnapshot`s
(already sorted chronologically, already scoped by the caller — see
"Cross-Organization Isolation" for where the scoping happens). Rules,
matching spec §40's explicit "no unsubstantiated interpretation of
changes":

- **`CONTRADICTED`**: reuses `app.intelligence.contradictions.
  detect_contradictions` unmodified — two `GENERAL_FACT` facts *within the
  same conversation*, same normalized `(subject, attribute)`, different
  normalized `value`. This is the exact same deterministic rule Phase 4
  already ships and already has its own tests; Phase 9 does not
  re-implement it.
- **`NEW`**: a `(subject, attribute)` pair's first-ever appearance across
  the ordered conversation group.
- **`CHANGED`**: the pair reappears in a later conversation with a
  different normalized value than its most recent prior occurrence, and
  neither occurrence is itself already flagged `CONTRADICTED` within its
  own conversation (avoiding double-reporting the same underlying data
  point two different ways).
- **`NOT_MENTIONED`**: a pair known from an earlier conversation is absent
  from a later one entirely.
- Identical normalized values across conversations produce **no item** —
  the diff only ever contains real differences, never a "no change"
  placeholder row.

Every item carries `current_fact_id`/`current_value` and
`prior_fact_id`/`prior_value` (both populated whenever both sides exist;
either genuinely `null` only when that side genuinely doesn't exist, e.g.
`NEW` has no prior, `NOT_MENTIONED` has no current) — never asserts a
change without pointing at the specific fact rows being compared.

**Verified with 7 pure unit tests** (`tests/longitudinal/
test_comparison.py`, no DB, no LLM): first-occurrence `NEW` with correct
evidence id; `CHANGED` across two conversations with both fact ids/values
asserted; identical-value pairs produce zero items; `NOT_MENTIONED` when a
later conversation omits a previously-known fact; a same-conversation
contradiction (`5mg`/`10mg` both asserted in one visit) is classified
`CONTRADICTED` with both fact ids present; case/whitespace normalization
(`"Ramipril"`/`"  ramipril  "`, `"5mg"`/`"5MG"`) is treated as equal per
`app.intelligence.contradictions`'s own existing normalization; two
different `(subject, attribute)` pairs in the same conversation are
tracked independently.

**Verified against a real, constructed multi-conversation scenario**
(direct unit-test construction, deliberately not depending on any real
LLM extraction run — the comparison mechanism itself is what's under test,
not the extraction pipeline, matching how `app.intelligence.contradictions`
was itself validated in Phase 4): the Ramipril dose 5mg→10mg scenario from
`docs/architecture/domain-model.md`'s own illustrative example, both as a
cross-conversation `CHANGED` case and as a same-conversation `CONTRADICTED`
case, both correctly classified.

## Follow-ups / Tasks

`GET/POST /conversations/{id}/tasks` (gated `task:read`/`task:create`),
`PATCH /tasks/{id}` (gated `task:update`, re-derives authorization from the
task's owning conversation — never reachable purely by guessing its UUID,
matching `app.intelligence.router`'s existing fact/evidence pattern).

**AI_EXTRACTED path**: `app.longitudinal.service.sync_ai_extracted_tasks`
idempotently creates one `FollowUpTask` per `ExtractedFact(category=
"task")` that doesn't already have one (matched by `source_fact_id`),
called on every task-list read — safe to call repeatedly, never
duplicates, never overwrites a task a human has since edited/closed.
Verified:

- **Automated**: `test_ai_extracted_task_is_synced_from_existing_
  extracted_fact` inserts a real `ExtractedFact(category="task",
  structured_value={description, assignee, due_date, ...})` directly,
  confirms the synced task carries `source: "ai_extracted"`,
  `source_fact_id` equal to the real fact's id, and the exact description/
  assignee/due_date; confirms a second list call does not duplicate it.
- **Live** (real Docker Compose, real Postgres): inserted a real
  `ExtractedFact(category="task", description="Order follow-up blood
  test", assignee="Dr. Smith", due_date="in 2 weeks")` directly against the
  running database, then confirmed via a real `GET /conversations/{id}/
  tasks` call that the task appears with `source: "ai_extracted"` and the
  correct `source_fact_id` — the real API, real Postgres, no mocking.

**USER_CREATED path**: `POST /conversations/{id}/tasks` creates a task
with `source_fact_id: null`. Verified:

- **Automated**: `test_user_created_task_full_lifecycle` creates a task,
  confirms `source: "user_created"`/`source_fact_id: null`, updates it to
  `status: "done"` via `PATCH /tasks/{id}`, confirms the list reflects the
  new status.
- **Live**: created a real task ("Call patient back", assignee "Nurse
  Jones", due "tomorrow") via curl, listed it, updated it to `done` via
  `PATCH`, and confirmed persistence across a real `docker compose restart
  backend postgres` (see "Restart Persistence" below).

**Authorization**: `test_task_endpoints_require_permission_and_are_org_
scoped` confirms Bob (Org B) gets `404` (not 403 — matching the existing
"don't confirm existence to an unauthorized caller" convention) attempting
to list, create on, or `PATCH` a task belonging to Alice's (Org A)
conversation, including guessing a real task UUID directly.
`test_update_task_rejects_invalid_status` confirms an invalid status value
is rejected with `422` (Pydantic enum validation on `UpdateTaskRequest
.status`, never silently accepted).

## API / OpenAPI

New endpoints: `GET /conversations/{id}/related`, `GET
/external-references/{ref}/timeline`, `GET /external-references/{ref}/
comparison`, `GET/POST /conversations/{id}/tasks`, `PATCH /tasks/{id}`.
`frontend/openapi.json`/`schema.d.ts` regenerated against a live backend
instance (a locally-run `uvicorn`, curled — the exact method CI's
drift-check job uses, after the formatting bug described in "Bugs Found
and Fixed" was corrected). CI's "OpenAPI TS client drift check": **PASS**
on the final commit, both workflow runs.

## Database / Migrations

**One new migration this phase**: `0010_longitudinal_documentation` —
additive `follow_up_tasks` table only (FKs to `organizations`,
`conversations` [`ON DELETE CASCADE`], `extracted_facts` [`ON DELETE SET
NULL`], `users` ×2 [`ON DELETE SET NULL`]). Verified against a real
Postgres 16 container: `alembic upgrade head` applies the full
`0001→0010` chain cleanly on a fresh database (see "Fresh Install" below).
Timeline and Comparison required **no schema change at all** — both are
pure reads over Phase 2's `conversations.external_reference` and Phase 4's
`extracted_facts`.

## Authorization

| Endpoint group | Permission (new unless noted) |
|---|---|
| Timeline (`/conversations/{id}/related`, `/external-references/{ref}/timeline`), Comparison | `timeline:read` **(new)** |
| List conversation tasks | `task:read` **(new)** |
| Create a user task | `task:create` **(new)** |
| Update a task's status | `task:update` **(new)** |

Granted to: Manager (all four), User (all four), Reviewer (`timeline:read`,
`task:read`, `task:update` — reviewers can act on tasks flagged during
review but don't originate conversations), Auditor (`timeline:read`,
`task:read` only — read-only, matching its existing role definition).
System Admin has every permission via the existing `list(PERMISSIONS
.keys())` pattern. Template Manager and API Service Account were not
granted these (neither role touches conversation-level workflow today).

**Non-permission-holder denial verified live**: created a real user with
zero group/role memberships (`noperm_user`) against the live Docker
deployment and confirmed `403` on `/external-references/1/timeline`,
`/conversations/{id}/tasks` (GET), and `/conversations/{id}/related` —
matching the rigor of every prior phase's live authorization testing.

## Audit

`timeline.viewed` (organization id, conversation count), `task.created`
(task id, conversation id), `task.updated` (task id, new status) — IDs/
counts only, matching Phase 7 Audit viewer's existing verbosity. Verified
by inspection of every `record_event` call site added this phase (3 call
sites, all in `app.longitudinal.router`) — none pass task description,
assignee, or fact content.

## Security

No new attack surface beyond permission-gated read/write over existing and
one new table: every mutating endpoint requires CSRF (`require_csrf`,
unchanged pattern); `PATCH /tasks/{id}` re-derives authorization from the
task's owning conversation rather than trusting the task id alone (a task
is exactly as sensitive as its conversation); the Comparison endpoint
makes zero LLM calls and accepts no caller-supplied content beyond the
`external_reference` path parameter (used only as a `WHERE`-clause value
via SQLAlchemy's parameterized query construction — never string-
interpolated into raw SQL).

## Compliance / Dependencies / Containers / Licenses

**No new dependency was added this phase** (`backend/pyproject.toml` and
`frontend/package.json` are byte-identical to their pre-Phase-9 state —
verified via `git diff main -- backend/pyproject.toml
frontend/package.json` before any Phase 9 commit).

| Category | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies | 36 | 0 | 0 | 0 |
| Transitive (498 resolved packages) | 495 | 3 | 0 | 0 |
| Container images | 7 | 0 | 0 | 0 |
| AI models | 6 | 0 | 0 | 0 |

Identical to Phase 8's numbers (no dependency change). `compliance/
check_licenses.py` → **PASS**. CI's "License compliance" job: **PASS** on
both final workflow runs.

## Tests

**Backend**: 247 passed (231 pre-existing + 16 new), ruff clean, mypy
clean (136 source files).

New test breakdown (`tests/longitudinal/`, 16 tests across 3 files):
- `test_comparison.py` (7): pure-function determinism tests for all four
  classifications plus unchanged-value and normalization edge cases — no
  DB, no LLM.
- `test_timeline_and_isolation.py` (5): timeline grouping within one
  organization, the critical cross-organization isolation test (Timeline
  and Comparison endpoints both), the conversation-scoped "related"
  endpoint including the no-external-reference case.
- `test_tasks.py` (4): AI_EXTRACTED sync from a real inserted fact
  (including idempotency-on-repeat-read), USER_CREATED full lifecycle,
  organization-scoped authorization (404 on cross-org access/update
  attempts), invalid-status rejection.

**Frontend**: 21 pre-existing tests pass unchanged; tsc/eslint/`vite
build` all clean. No new frontend unit tests were added for the 2 new
Conversation-detail tabs (`LongitudinalPanel`, `TasksPanel`) — verified via
`tsc`/eslint/`vite build` passing and manual code review, matching every
prior phase's documented precedent for equally new, equally minimal
frontend surfaces (Phase 8's Admin pages had the identical disclosed gap).

## GitHub Actions

All 7 required checks green on the final commit (`e1d750b`), both
workflow runs (`33914087601`/`33914091701`):

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | PASS |
| Frontend (lint / typecheck / test / build) | PASS |
| Alembic migration (real Postgres) | PASS |
| OpenAPI TS client drift check | PASS |
| License compliance (direct + full transitive tree) | PASS |
| Docker build (backend + frontend + AI worker) | PASS |
| Container vulnerability scan (Trivy) | PASS |

One real CI-blocking issue was found and fixed this phase: the initial
`frontend/openapi.json`/`schema.d.ts` were generated by calling
`app.openapi()` in-process and pretty-printing the result, which produced
byte-different (but semantically identical) output from what CI's
drift-check curls from a live `uvicorn` — the first push failed that
check; fixed by regenerating from a locally-run `uvicorn` instance instead
(commit `e1d750b`), after which the check passed cleanly.

## Fresh Install

Validated for real against `docker compose` (`postgres`, `valkey`,
`migrate`, `backend`, `frontend` — excluding `ollama`/`model-manager`/
workers, matching every prior phase's fresh-install scope; this phase adds
no new provider/worker surface):

- `docker compose build migrate backend frontend` — all three images
  built successfully.
- `docker compose up -d postgres valkey migrate backend frontend` —
  `migrate` ran the full `0001→0010` chain against a fresh Postgres 16
  container (confirmed in logs: `... 0009_analytics_evaluation ->
  0010_longitudinal_documentation, follow_up_tasks (Phase 9: Longitudinal
  Documentation)`); backend and frontend both reached a running state with
  **no errors in either service's logs**.
- `python -m app.identity.bootstrap_admin` (via `docker compose exec
  backend`) created the first System Admin user.
- A dedicated setup script (run via `docker compose exec backend python`)
  created two real organizations and two real users (one per organization,
  standard `User` role) directly against the live database, mirroring the
  test suite's `seeded` fixture exactly.
- Real HTTP (curl, session-cookie-authenticated) walkthrough covering
  every scenario described in "Cross-Organization Isolation," "Follow-ups
  / Tasks," and "Authorization" above — all against the real running
  stack, not mocked.

## Phase 8 Upgrade Validation

Phase 9 **does** add a real migration (`0010_longitudinal_documentation`).
Both halves of the upgrade path were actually run against a real running
stack:

1. **Schema**: `alembic upgrade head` from a Phase-8-equivalent database
   (verified via the standalone `0009→0010` step within the full fresh-
   install `0001→0010` chain) applies cleanly — a purely additive new
   table, no existing column touched, no data loss.
2. **RBAC reseed**: `python -m app.identity.seed` was run against the live
   Docker deployment after the fresh-install bootstrap (which itself calls
   the same seed function) and again standalone via `docker compose exec
   backend python -m app.identity.seed` — the second, standalone run
   printed `RBAC seed applied (permissions/roles created or already up to
   date).` with no duplicate-row error, confirming idempotency for the new
   `timeline:read`/`task:read`/`task:create`/`task:update` permission
   codes.

## Restart Persistence

`docker compose restart backend postgres` — the conversation created
before the restart (`GET /conversations/{id}`) and the user-created task's
`status: "done"` update made before the restart (`GET /conversations/{id}/
tasks`) were both confirmed present/correct afterward via real API calls
using the same, still-valid session (Valkey was not restarted) — not
assumed from `docker volume ls`.

## Known Limitations

- **The temporal diff only compares `GENERAL_FACT` items** —
  `DECISION`/`TASK` category facts are not part of the NEW/CHANGED/
  NOT_MENTIONED/CONTRADICTED comparison (Follow-ups/Tasks already surface
  `TASK` facts through their own dedicated view). A future phase wanting
  "this decision changed between visits" would need its own normalized
  key shape, analogous to `GeneralFactItem`'s `(subject, attribute)` pair
  — not built here since neither `DecisionItem` nor `TaskItem` has an
  obvious stable identity key.
- **Comparison is recomputed on every request, not cached/precomputed** —
  fine at the expected scale of one patient/case/client's conversation
  history; would need memoization or a persisted result table at much
  larger group sizes. Documented in `future-considerations.md`.
- **`FollowUpTask.due_date` is a free-form, unparsed string** (mirrors
  `TaskItem.due_date` exactly, including accepting `"NOT_MENTIONED"` or
  natural-language phrases like "in 2 weeks") — no due-date sorting or
  reminder feature is possible until a future phase decides how to parse
  these, which the spec does not require now.
- **No notification/reminder/email system for tasks** — intentional, per
  the phase brief (Phase 10/Integrations territory). A task going overdue
  triggers nothing; a user must open the Tasks tab to see it.
- **No frontend unit tests for the 2 new Conversation-detail tabs** —
  verified via `tsc`/eslint/`vite build` passing and manual code review,
  matching every prior phase's identical, explicitly disclosed gap for its
  own new frontend surfaces.
- **The multi-conversation comparison scenario was validated via direct
  unit-test construction of fact snapshots, not a real end-to-end LLM
  extraction run across multiple real conversations** — this tests the
  comparison mechanism itself (the genuinely new code this phase adds)
  rather than re-validating Phase 4's extraction pipeline, which already
  has its own dedicated test coverage; the live walkthrough did insert a
  real `ExtractedFact` row directly (the same mechanism a real extraction
  run would populate) to verify the AI_EXTRACTED task-sync path end-to-end
  against the real database.

## Bugs Found and Fixed This Phase

- **`frontend/openapi.json` formatting mismatch vs. CI's drift-check**:
  the schema content and the generated TS client were correct from the
  first commit, but the file was pretty-printed (`indent=2`, one key per
  line, ~11,300 lines) rather than the exact compact single-line format
  FastAPI serves and CI's drift-check curls and diffs byte-for-byte. Found
  by watching the first CI run fail the "OpenAPI TS client drift check"
  job; fixed by regenerating `openapi.json` from a locally-run `uvicorn`
  instance (curling it, the same method the CI job itself uses) instead of
  calling `app.openapi()` and dumping it manually — `schema.d.ts` was
  byte-identical before and after, confirming this was purely a formatting
  bug, not a real schema drift. This is exactly the kind of gap process
  rule 3 ("real testing over assumed correctness") exists to catch, and it
  was caught by watching the actual CI run rather than assuming the
  in-process generation would match.
- **`db.refresh()` needed after `db.commit()` in `PATCH /tasks/{id}`**:
  the first draft of `update_task_endpoint` called `db.commit()` then
  immediately `FollowUpTaskResponse.model_validate(task)`, which raised a
  `MissingGreenlet` error accessing `updated_at` (a server-computed
  `onupdate=func.now()` column expired after the `UPDATE` flush, requiring
  an async refresh before synchronous Pydantic attribute access). Found by
  the endpoint's own automated test
  (`test_user_created_task_full_lifecycle`) failing immediately on first
  run — fixed by adding `await db.refresh(task)` before
  `model_validate`, matching the exact pattern already used in
  `app.conversations.router.update_conversation_endpoint`.

## Open Risks

None new this phase. The Ollama container's accepted CRITICAL finding from
Phase 4 (`compliance/container-inventory.yml`'s `ollama/ollama` entry)
remains open and tracked exactly as Phase 4-8 left it — this phase makes
no LLM calls and does not touch the LLM provider's container image at all.

## Architecture Deviations

None from the phase brief's explicit scope. The one design decision worth
naming explicitly: `CONTRADICTED` in the Comparison output is defined as a
*same-conversation* contradiction (reusing Phase 4's existing rule
directly) rather than a new *cross-conversation* contradiction concept —
this was a deliberate interpretation of the spec's four-state list, chosen
because it lets Phase 9 reuse a proven, already-tested deterministic rule
verbatim rather than inventing a new one, and because a genuine
same-conversation contradiction (e.g. two different doses stated in one
visit) represents unresolved uncertainty in the underlying data that
should be surfaced distinctly from an ordinary `CHANGED` value update
across time. No new ADR was added — this follows directly from ADR-0026's
(contradiction detection) existing precedent.

## Deferred Items

See `docs/architecture/future-considerations.md`'s new "Phase 9 additions":
Service Accounts/API/Webhooks/Backups/GPU-metrics dashboard (later-phase
roadmap items); notification/reminder/email for tasks (never, per the
phase brief); decision/task comparison; comparison result caching;
due-date parsing; fact-deletion evidence-loss UX for tasks.

## Git / PR / Merge Status

- Branch: `phase-9-longitudinal-documentation`, off `main` at `b2d55a9`.
- PR: [#16](https://github.com/ley338-gif/VocaDox/pull/16) — "Phase 9:
  Longitudinal Documentation (Timeline, Comparison, Follow-ups/Tasks)".
- Commits: `99b2a25` (backend: Timeline/Comparison/Follow-ups-Tasks
  foundation + tests), `4d435e1` (frontend: Timeline/Comparison/Tasks UI +
  OpenAPI regeneration), `251654b` (documentation), `e1d750b` (fix:
  OpenAPI drift-check formatting).
- All 7 required GitHub Actions checks: **green** on both workflow runs
  for the final commit (`e1d750b`).
- **Merge: performed**, matching Phase 5/6/7/8's precedent. Every
  merge-gate condition in the phase brief was independently verified:
  Timeline correctly groups conversations sharing an external reference
  within one organization; the cross-organization same-external-reference
  isolation test explicitly passes (both automated and live); comparison
  logic is deterministic and produces correct, evidence-traceable
  CHANGED/NEW/NOT_MENTIONED/CONTRADICTED classifications verified against
  a real multi-conversation test scenario; follow-ups/tasks work for both
  AI_EXTRACTED (linked to a real originating fact, verified live) and
  USER_CREATED paths; no regression in Phases 0-8 (247/247 tests,
  including all 231 pre-existing; 21/21 frontend); fresh install/restart
  persistence validated against real infrastructure; the Phase 8→9 upgrade
  path (real schema migration + idempotent RBAC reseed) validated against
  a real running stack; 0 blocked/0 unknown licenses; all CI green;
  documentation is current.

## Recommendation

**GO for Phase 10.** Every roadmap §73 Phase 9 item — Timeline, external
reference grouping, conversation comparison, changes, follow-ups, tasks —
has a working, permission-gated, real implementation. The phase's most
important risk (cross-organization data leakage via a coincidentally
shared `external_reference` string) was verified not to occur, through
both a dedicated automated test and a real live Docker walkthrough with
two genuinely separate organizations. The comparison mechanism is fully
deterministic and evidence-traceable, with no LLM narrative anywhere in
the code path, matching spec §40's explicit constraint. No regression to
any prior phase's functionality (247/247 backend, 21/21 frontend). One
process-rule-3 catch this phase (the OpenAPI formatting mismatch) was
found by watching a real CI run rather than assumed away, and fixed before
merge. No new open risk was introduced; the dependency set is completely
unchanged.
