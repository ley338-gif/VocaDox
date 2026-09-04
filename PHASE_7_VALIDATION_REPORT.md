# Phase 7 Validation Report: Administration (Admin Portal)

## Executive Summary

Phase 7 builds the Admin Portal (`/admin`) the master specification's
roadmap §73 and §48 describe: a real, permission-gated admin UI +
backend API consolidating and exposing management surfaces over the
domains built in Phases 0-6 — Dashboard, Users, Groups, Organizations,
Authentication, Models, Speech, Diarization, Profiles, Templates,
Prompts, Jobs, Workers, Storage, Retention, Audit, About & Licenses. This
is deliberately a CRUD/visibility/configuration phase, not a new-domain
phase: **no new database tables or columns were added** — every admin
surface operates on models that already existed (`users`/`groups`/
`roles`/`permissions`/`organizations` from Phase 1, `retention_policies`
from Phase 2, `processing_jobs`/`processing_runs` from Phase 3,
`templates`/`prompts`/`model_profiles`/`processing_profiles` from Phase
6, `audit_events` from Phase 1).

Real gaps flagged by prior phases' validation reports were closed:
`POST /organizations` (flagged by Phase 5/6 as missing), a dedicated
Prompts admin page (the Phase 6 backend API existed with no UI), and a
UI to set `speech_provider_config`/`diarization_provider_config` per
Processing Profile version (Phase 6's own Known Limitation). Two new
permission codes were added (`retention:read`/`retention:write`); every
other admin page reuses a permission that already existed and already
scoped that exact resource — no parallel authorization system was
introduced.

Every automated check is green on the final commit, both workflow runs:
211 backend tests (184 pre-existing + 27 new), ruff/mypy clean; 21
pre-existing frontend tests unchanged, tsc/eslint/`vite build` clean, no
OpenAPI drift. Fresh install, a real browser walkthrough of every new
admin page, non-admin denial (403) on every new endpoint, restart
persistence, and the Phase 6→7 upgrade path (`python -m app.identity
.seed`, idempotent) were all validated against a real `docker compose`
stack — not just the fast in-process test suite. License compliance:
PASS, 0 blocked/0 unknown, byte-identical to Phase 6's baseline (**no new
dependency was added this phase, in either `backend/pyproject.toml` or
`frontend/package.json`**).

## Scope

Implemented (maps to the phase brief's roadmap §73 list):

1. **Admin Portal shell** (`frontend/src/components/AdminLayout.tsx`): a
   persistent sidebar organized into the spec §48 section groups
   (Dashboard / MANAGEMENT / AI / OPERATIONS / SECURITY / SYSTEM), each
   link hidden unless the current user has that section's permission.
   The sidebar is a convenience only — every page is independently
   wrapped in `RequirePermission` in `App.tsx` matching exactly the
   permission its backend endpoint enforces.
2. **Users** (`app.identity.router`'s new `/admin/users` endpoints):
   list/create/deactivate (never hard-delete)/assign-groups, gated by
   the pre-existing `user:manage` permission.
3. **Groups** (`/admin/groups`): create/rename/assign-roles/view-members,
   gated by the pre-existing `group:manage` permission.
4. **Organizations**: `POST /organizations` + `GET/POST
   /organizations/{id}/members`, gated by the pre-existing
   `organization:manage` permission — closes the "organization creation
   has no HTTP endpoint" gap flagged by the Phase 5 and Phase 6
   validation reports.
5. **Authentication**: a read-only admin page showing which
   `AuthProviderType` is actually implemented (LOCAL only) vs.
   interface-only (OIDC/LDAP_AD/REVERSE_PROXY) — no new provider type
   was implemented this phase, matching Phase 1's explicit scope
   boundary.
6. **Models/Speech/Diarization** (new `GET /admin/models` +
   `GET /admin/providers/llm`, gated by the pre-existing `provider:read`
   permission): aggregates the three provider `.status()` checks Phase
   3/4 already built into one page. No model install/download UI — links
   to the existing Phase 3.1 `model-manager` CLI instead.
7. **Profiles** (Model Profiles + Processing Profiles,
   `app.profiles.router`, Phase 6): integrated into the Admin Portal
   shell and extended with a "New draft version" form that sets
   `speech_provider_config`/`diarization_provider_config` on a new
   `ProcessingProfileVersion` — closing the exact gap Phase 6's own
   validation report flagged ("Speech/Diarization profiles still
   Settings-driven... no UI to edit these per-profile hints").
8. **Templates** (`app.templates.router`, Phase 6): moved from a
   standalone page into the Admin Portal shell.
9. **Prompts**: a new dedicated admin page for the Phase 6
   DRAFT→TEST→PUBLISHED→RETIRED lifecycle — the backend API
   (`app.templates.router`'s `prompts_router`) existed since Phase 6
   with no dedicated UI until now.
10. **Jobs** (new `GET /admin/jobs`, `POST /admin/jobs/{id}/retry`,
    gated `system:admin`): real, global, cross-organization
    `ProcessingJob` listing with status/type filters. Retry reuses the
    existing retry mechanism (`app.processing.service
    .retry_failed_job`, mirroring `fail_job`'s retry-dispatch path) —
    only a terminally FAILED job is eligible.
11. **Workers** (new `GET /admin/workers`, gated `system:admin`): derived
    purely from `ProcessingJob.worker_id`/status/timestamps grouped by
    the three existing worker roles (`worker-speech`/
    `worker-diarization`/`worker-extraction`) — no new worker-registry
    table.
12. **Storage** (new `GET /admin/storage`, gated `system:admin`): real
    recursive directory-size scan of the media storage root and model
    volume, plus real `shutil.disk_usage` filesystem totals (with a
    nearest-existing-ancestor fallback for a not-yet-created root).
13. **Retention** (new `GET/POST /admin/retention-policies`, `PATCH
    .../{id}`, new `retention:read`/`retention:write` permissions):
    real CRUD over `RetentionPolicy` rows that have existed since Phase
    2 with no admin UI until now. **No automated enforcement/cleanup
    scheduler was added** — that remains Phase 11's "Retention Cleanup"
    scope; this phase manages the policy definitions only.
14. **Audit** (new `app.audit.router`): filterable/paginated read-only
    viewer over `audit_events` accumulated since Phase 1, gated by the
    pre-existing `audit:read` permission. A pure viewer — no change to
    what gets audited.
15. **About & Licenses** (new `GET /admin/about`, gated `system:admin`):
    application version + a license-compliance inventory summary
    (computed by scanning the existing `compliance/*.yml` files with a
    regex, no new YAML-parsing runtime dependency) + a
    `THIRD_PARTY_NOTICES.md` excerpt.
16. **Dashboard** (new `GET /admin/dashboard`, gated `system:admin`):
    real, live-checked component health (API/Postgres/Valkey/Speech/
    Diarization/LLM — never a fabricated "Healthy"), real queue counts,
    a narrow hardware snapshot (CPU count via `os.cpu_count()`, RAM via
    a Linux-only `/proc/meminfo` read, GPU/VRAM reusing Phase 3's
    existing `app.providers.device.detect_device_capabilities` — no
    `psutil` dependency added). The response schema structurally cannot
    carry conversation/fact/transcript/document content.
17. **New RBAC permissions**: `retention:read`/`retention:write`
    (granted to Manager + System Admin). Every other new admin endpoint
    reuses a permission that already existed since Phase 1
    (`user:manage`, `group:manage`, `organization:manage`, `audit:read`,
    `system:admin`) or Phase 3/6 (`provider:read`, `template:read`/
    `write`, `processing-profile:read`/`write`) — no redundant parallel
    permission system.
18. **Tests**: 27 new backend tests (`tests/administration/`) covering
    every new endpoint's happy path and its 403-on-missing-permission
    case. No new database migration was needed, so no migration test.
19. **Documentation**: `docs/admin/admin-portal.md` (new, full
    section-by-section reference), updates to `docs/admin/README.md`,
    `docs/admin/retention.md`, `docs/architecture/future-considerations
    .md` (new "Phase 7 additions" section), `docs/architecture/model-
    management-foundation.md`, `docs/architecture/domain-model.md`, and
    `backend/app/administration/README.md` (no longer a Phase 0
    placeholder).

**Explicitly out of scope, not implemented** (per the roadmap): the
Evaluation Lab/model comparison (Phase 8), cross-conversation
Longitudinal Documentation (Phase 9), Service Accounts/API scopes/
Webhooks (Phase 10), automated Retention Cleanup worker/Backup-Restore/
GPU-metrics dashboard (Phase 11), final hardening audit (Phase 12).
Dictionaries (appears in the spec's illustrative mockup nav but not in
the roadmap §73 bullet list) was deliberately deferred, not built even as
a placeholder. See `docs/architecture/future-considerations.md`'s "Phase
7 additions" for the itemized list.

## Architecture

No new domain package's data model — Phase 7 is additive endpoints/UI
over Phases 1-6's existing packages, plus one new thin package
(`app.administration.service`/`.schemas`, extending the pre-existing
`app.administration.router` that Phase 3 started for provider-status
endpoints) and one new domain-adjacent router (`app.audit.router`, the
first HTTP surface for the `app.audit` package that has existed since
Phase 1). See `docs/admin/admin-portal.md` for the full page-by-page
reference (permission code, backend endpoint, what's real vs. what's a
known limitation) and `docs/architecture/future-considerations.md`'s new
"Phase 7 additions" section for what was deliberately deferred.

## Admin Portal Navigation

`frontend/src/components/AdminLayout.tsx` renders exactly the spec §48
structure:

```
Dashboard
MANAGEMENT: Users, Groups, Organizations, Templates
AI: Models, Speech, Diarization, Processing Profiles, Prompts
OPERATIONS: Jobs, Workers, Storage, Retention
SECURITY: Authentication, Audit
SYSTEM: About & Licenses
```

Verified via a real browser session against a live Docker Compose stack
(not just unit tests): every link is visible when logged in as the
seeded System Admin, and every page renders real backend data (see
"Fresh Install" below for the exact walkthrough).

## Dashboard

`GET /admin/dashboard` (gated `system:admin`) returns real, live-checked
values — verified against the real stack:

```json
{"components":[{"name":"api","healthy":true},{"name":"postgresql","healthy":true},
{"name":"valkey","healthy":true},{"name":"speech_provider","healthy":true},
{"name":"diarization_provider","healthy":true},{"name":"llm_provider","healthy":true}],
"queue":{"queued":0,"running":0,"failed":0},
"hardware":{"cpu_count":16,"total_ram_mb":15543,"cuda_available":false,...},
"application_version":"0.0.1"}
```

Every field is a boolean/count/string label — the response schema
(`DashboardResponse`) has no field capable of carrying conversation/fact/
transcript/document content, verified both by inspection and by a test
(`test_dashboard_shows_real_component_health_and_queue_counts`) asserting
the exact key set. A non-admin user (`alice`, standard "User" role) gets
403 (`test_dashboard_requires_system_admin`), verified via both the
automated suite and a live `curl` against the real deployment.

## Users / Groups / Organizations

Full CRUD/assignment flows, verified end-to-end via both the automated
test suite and a real browser session:
- Created a user (`dave`/`clinician1`) via the admin UI, verified it
  appears in the list, deactivated it via `PATCH .../is_active=false`,
  and confirmed the deactivated user can no longer log in (401).
- Created a group ("Psychotherapy"), assigned it the Reviewer role,
  added a user to it via the Users page's group-assignment UI, verified
  the group's member list updated.
- `POST /organizations` (closing the pre-existing gap): created "General
  Medicine" via both a direct `curl` call and the admin UI, verified
  duplicate-slug rejection (409), added a member via `POST
  /organizations/{id}/members`, verified duplicate-membership rejection
  (409) — all exercised live in the browser (add-member flow screenshotted
  via `get_page_text`, showing the real member list update after the
  action).

## Authentication

Read-only page listing `AuthProviderType.LOCAL` as active and
`OIDC`/`LDAP_AD`/`REVERSE_PROXY` as "not implemented" — matches Phase 1's
actual, unchanged implementation state exactly (verified by reading
`app.identity.auth_providers`: only `LocalAuthProvider` exists). No new
auth provider type was implemented.

## Models / Speech / Diarization / Profiles / Templates / Prompts

- `GET /admin/models` aggregates the three existing provider `.status()`
  calls; verified live against the real stack (fake providers, CI/dev
  default) returning `provider: "fake"`, `installed: true` for all
  three — never a fabricated "Healthy" for a provider that isn't
  actually configured (Phase 3's "Not installed, not fake Healthy"
  principle carried forward).
- **Processing Profiles gap closed**: created a new draft
  `ProcessingProfileVersion` on the seeded "Meeting" profile with
  `speech_provider_config: {"model": "faster-whisper-large-v3"}` and
  `diarization_provider_config: {"min_speakers": 2, "max_speakers": 6}`
  via the admin API, then confirmed via the real browser UI (after a page
  reload/expand) that the new v2 draft version displays exactly that
  configuration with a "Publish" action available — the first UI to ever
  set these fields, previously REST-API-only.
- Templates: unchanged Phase 6 functionality, now living inside the
  Admin Portal shell instead of a standalone page.
- Prompts: new page exercising the existing DRAFT→TEST→PUBLISHED→RETIRED
  lifecycle backend (list prompts/versions, publish a draft — which
  auto-retires the prior published version per the existing
  non-destructive-versioning rule).

## Jobs / Workers

- `GET /admin/jobs`: verified against a real queued `ProcessingJob`
  (created by `POST .../process/transcript` against a real conversation)
  — the job appears in the global admin list with the correct
  conversation id, status, and filters work (`?status=queued`).
- Retry: forced a job to FAILED directly in the test DB, called `POST
  /admin/jobs/{id}/retry`, confirmed it returns to `queued` with
  `attempt` reset to 0 and a fresh outbox entry written; confirmed a
  second retry attempt on the now-QUEUED job is rejected (409) — only a
  terminally FAILED job is eligible, matching `cancel_queued_job`'s
  "only QUEUED jobs can be cancelled cleanly" precedent for the mirror
  case.
- `GET /admin/workers`: verified the three roles
  (`worker-speech`/`worker-diarization`/`worker-extraction`) are
  reported with real `queued_jobs`/`running_jobs` counts reflecting an
  actually-queued job — no fabricated "connected" status.

## Storage / Retention

- `GET /admin/storage`: verified against the real Docker deployment —
  returned real, non-zero disk totals/free space for both the media
  storage root and the model volume (using the nearest-existing-ancestor
  fallback since neither directory had been created yet on the fresh
  install).
- Retention: created a real `RetentionPolicy` ("Standard 90 days", 90
  days, don't delete source/derived) via `curl`, confirmed it appears in
  `GET /admin/retention-policies` and in the real browser UI, updated it
  via `PATCH` (retention_days→180, active→false), confirmed the
  untouched field (`delete_source_media`) was preserved. Verified `bob`
  (standard "User" role, no `retention:read`) gets 403.
  **No automated enforcement/cleanup worker exists** — this is
  explicit, documented management of the policy definitions only.

## Audit

`GET /admin/audit-events`, verified against the real stack: listed real
`login`/`login_failed`/`user.created`/`template.published`/
`prompt.published`/`processing_profile.published` events accumulated
during this session's own testing, filterable by `event_type`/
`username`. Every event's `event_metadata` was inspected and contains
only ids/version numbers/field-name lists — never conversation content
(verified both by a test assertion and by reading every `record_event`
call site across the codebase, unchanged from prior phases' hard rule).
`bob`/`alice` (standard "User" role, no `audit:read`) get 403.

## About & Licenses

`GET /admin/about`: in the real Docker container, correctly reports
`license_summary: {}` and `"THIRD_PARTY_NOTICES.md not found."` — an
**honest, documented limitation**, not a bug: `backend/Dockerfile`'s
build context is `backend/` only (one level below the repo root where
`compliance/`/`THIRD_PARTY_NOTICES.md` actually live), and this phase
deliberately did not restructure the Docker build to ship them (see
Known Limitations). In a local dev checkout (`resolve_repo_root()`'s
fallback), the same endpoint returns the real compliance summary and
notices excerpt — verified by unit test.

## API / OpenAPI

New endpoints: `GET/POST/PATCH /admin/users[/{id}]`, `GET/POST/PATCH
/admin/groups[/{id}]`, `GET /admin/roles`, `POST /organizations`, `GET/
POST /organizations/{id}/members`, `GET /admin/audit-events[/event-
types]`, `GET /admin/dashboard`, `GET /admin/models`, `GET
/admin/providers/llm`, `GET /admin/jobs`, `POST /admin/jobs/{id}/retry`,
`GET /admin/workers`, `GET /admin/storage`, `GET/POST/PATCH
/admin/retention-policies[/{id}]`, `GET /admin/about`.
`frontend/openapi.json`/`schema.d.ts` regenerated against a live backend
instance (curl a running uvicorn's `/openapi.json`, the exact method
CI's drift-check job uses) — CI's "OpenAPI TS client drift check": PASS
on both final workflow runs.

## Database / Migrations

**No new migration this phase.** Every admin surface operates on tables
that already existed (`users`/`groups`/`roles`/`permissions`/
`user_group_memberships`/`group_roles`/`role_permissions`/
`organizations`/`organization_memberships` from `0002_identity_rbac`;
`retention_policies` from `0003_conversation_capture`; `processing_jobs`
from `0004_speech_diarization`; `templates`/`prompts`/`model_profiles`/
`processing_profiles`/versions from `0008_templates_profiles`;
`audit_events` from `0002_identity_rbac`). Verified against a real
Postgres 16 container: the full `0001→0008` chain applied cleanly on a
fresh install with no Phase-7-specific step.

## Authorization

Every new endpoint gated by `app.identity.deps.require_permission`.
`retention:read`/`retention:write` are the only genuinely new permission
codes; every other new admin endpoint reuses a permission that already
existed and already scoped that exact resource:

| Section | Permission (pre-existing unless noted) |
|---|---|
| Dashboard, Jobs, Workers, Storage, Authentication, About | `system:admin` |
| Users | `user:manage` |
| Groups, Roles (read) | `group:manage` |
| Organizations | `organization:manage` |
| Templates, Prompts | `template:read`/`write` |
| Models, Speech, Diarization | `provider:read` |
| Processing Profiles | `processing-profile:read`/`write` |
| Retention | `retention:read`/`write` **(new)** |
| Audit | `audit:read` |

**Non-admin denial verified for real**, matching the rigor of every
prior phase's authorization testing: `alice` (standard "User" role) gets
403 on `/admin/dashboard`, `/admin/users`, `/admin/groups`,
`/organizations` (POST), `/admin/jobs`, `/admin/jobs/{id}/retry`,
`/admin/workers`, `/admin/storage`, `/admin/models`, `/admin/about`;
`bob` (also "User" role) gets 403 on `/admin/retention-policies` and
`/admin/audit-events` — verified by 12 dedicated 403 tests across
`tests/administration/` AND by live `curl` calls against the real Docker
deployment with a real, freshly-created non-admin user (`clinician1`).

## Audit (of the audit trail itself)

New audit event types this phase: `user.created`, `user.updated`,
`processing_job.retried`. Verified via inspection: none carry
conversation/fact/transcript/document content, only ids/field-name
lists — consistent with the hard rule unchanged since Phase 1.

## Security

No new attack surface beyond what permission-gated CRUD over existing
models implies: every mutating endpoint requires CSRF (`require_csrf`,
unchanged pattern); `LocalFilesystemStorage`'s existing path-traversal
protections are untouched (Storage page only reads `Settings`-configured
roots, never a caller-supplied path); the About page's file reads are
fixed, server-controlled paths (`THIRD_PARTY_NOTICES.md`,
`compliance/*.yml`), never derived from request input.

## Compliance / Dependencies / Models / Containers / Licenses

**No new dependency was added this phase** (`backend/pyproject.toml` and
`frontend/package.json` are byte-identical to their pre-Phase-7 state —
verified via `git diff b407484 HEAD`).

| Category | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies | 36 | 0 | 0 | 0 |
| Transitive (498 resolved packages) | 495 | 3 | 0 | 0 |
| Container images | 7 | 0 | 0 | 0 |
| AI models | 6 | 0 | 0 | 0 |

Byte-identical to Phase 6's final baseline. `compliance/check_licenses.py`
→ **PASS**. CI's "License compliance" job: **PASS** on both final
workflow runs.

## Tests

**Backend**: 211 passed (184 pre-existing + 27 new), ruff clean, mypy
clean (124 source files).

New test breakdown (`tests/administration/`, 27 tests across 9 files):
- `test_users.py` (3): list requires `user:manage`; full create/view/
  deactivate lifecycle including the deactivated-user-can't-login proof;
  duplicate-username rejection.
- `test_groups.py` (2): list requires `group:manage`; create + role
  assignment + member management + rename lifecycle.
- `test_organizations.py` (2): create requires `organization:manage`;
  create + duplicate-slug rejection + member add + duplicate-member
  rejection.
- `test_audit.py` (2): list requires `audit:read`; real login events
  listed/filtered, metadata never carries prohibited content, event-types
  endpoint.
- `test_dashboard.py` (2): requires `system:admin`; real component
  health/queue-count/hardware fields, exact response-key-set assertion
  (privacy rule).
- `test_models.py` (3): overview requires `provider:read`; real fake-
  provider status for speech/diarization/llm; standalone LLM status
  endpoint.
- `test_jobs.py` (4): list requires `system:admin`; a real queued job is
  listed and filterable; retry requeues a forced-FAILED job and rejects
  a second retry on the now-QUEUED job; retry endpoint requires
  `system:admin`.
- `test_workers.py` (2): requires `system:admin`; a real queued job is
  reflected in the correct worker role's counts.
- `test_storage.py` (2): requires `system:admin`; real non-zero disk
  totals.
- `test_retention.py` (3): write requires `retention:write`; full CRUD
  lifecycle with partial-update field preservation; read requires
  `retention:read`.
- `test_about.py` (2): requires `system:admin`; real app version +
  well-formed (possibly-empty) license summary.

**Frontend**: 21 pre-existing tests pass unchanged; tsc/eslint/`vite
build` all clean. No new frontend unit tests were added for the ~20 new
admin pages — verified via `tsc`/eslint/`vite build` passing, a real
Docker Compose browser walkthrough (see Fresh Install below), and manual
code review, matching Phase 4/5/6's own documented precedent for
equally new, equally minimal frontend surfaces.

## GitHub Actions

All 7 required checks green on the final commit (`872dcb2`, merged as
`85d658d`), both workflow runs:

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | PASS |
| Frontend (lint / typecheck / test / build) | PASS |
| Alembic migration (real Postgres) | PASS |
| OpenAPI TS client drift check | PASS |
| License compliance (direct + full transitive tree) | PASS |
| Docker build (backend + frontend + AI worker) | PASS |
| Container vulnerability scan (Trivy) | PASS |

No real CI-blocking issue was found this phase (unlike Phase 6's
fastapi/starlette version-drift and OpenAPI-baseline issues) — the
dependency set was completely unchanged, so no upstream drift was
possible.

## Fresh Install

Validated for real against `docker compose` (excluding `ollama`/
`model-manager`, matching every prior phase's fresh-install scope —
extraction/speech/diarization default to `fake` providers):

- `docker compose down -v` → `docker compose build migrate backend
  worker-speech worker-diarization worker-extraction frontend` — all
  images built successfully.
- `docker compose up -d postgres valkey migrate backend worker-speech
  worker-diarization worker-extraction frontend` — `migrate` ran the
  full `0001→0008` chain against a fresh Postgres 16 container; all
  seven services reached a running/healthy state; **no errors in any
  service's logs** (checked backend + all three workers).
- `python -m app.identity.bootstrap_admin` created the first System
  Admin user.
- Real HTTP + browser walkthrough end-to-end (see the section-by-section
  detail above): login as System Admin → full Admin Portal navigation
  renders with real data on every page → created a user, a group with a
  role assignment, an organization with a member, a retention policy →
  verified every new admin endpoint 403s for a freshly-created
  non-admin user (`clinician1`) → created a real queued `ProcessingJob`
  via the standard conversation/process flow and confirmed it appears in
  the admin Jobs/Workers views → created a new Processing Profile draft
  version with real speech/diarization JSON config via both the API and
  the browser UI, confirmed it displays correctly.

## Phase-6 Upgrade Validation

Since Phase 7 added no new migration, the upgrade path is exactly:
`alembic upgrade head` (a no-op against an already-Phase-6 database) +
`python -m app.identity.seed` (idempotent RBAC seed update, adding
`retention:read`/`retention:write`). **Both were actually run against
the live fresh-install stack** (the reseed CLI was run a second time,
after `bootstrap_admin` had already applied it once, to explicitly prove
the standalone Phase-6→7 upgrade path — not just bootstrap's internal
call to the same function) and confirmed idempotent (`SELECT code FROM
permissions WHERE code LIKE 'retention%'` returned exactly the 2
expected rows, no duplicates, no error). This is a stronger validation
than a same-schema-with-real-data rehearsal alone, since no schema
change exists to rehearse — the real risk surface (RBAC seed
idempotency) was exercised directly.

## Restart Persistence

`docker compose restart backend postgres` — the organization, retention
policy, and both users created before the restart were confirmed
byte-identical via real `GET /organizations`, `GET
/admin/retention-policies`, and `GET /admin/users` calls afterward (using
the same, still-valid session — Valkey was not restarted), not assumed
from `docker volume ls`.

## Known Limitations

- **No RAM figure beyond a Linux-only `/proc/meminfo` read**; no `psutil`
  dependency was added (narrow scope, matching Phase 3's "avoid building
  a hardware inventory platform" principle). Windows/macOS dev
  environments see `total_ram_mb: null`, not a fabricated value.
- **Storage's directory-size scan is a synchronous full filesystem
  walk** — real, not fabricated, but would not scale well to a very
  large media volume at today's implementation; a future phase should
  cache totals or compute them via a background job.
- **About & Licenses shows no compliance data in the production
  container image** — `compliance/`/`THIRD_PARTY_NOTICES.md` are outside
  `backend/Dockerfile`'s build context (`backend/` only); the endpoint
  honestly reports "not found" rather than restructuring the Docker
  build for one info page this phase.
- **No `SpeechProfile`/`DiarizationProfile` database entity** — Phase 7
  added the UI to edit the existing small JSON hint fields per
  Processing Profile version, not a real named/reusable entity; still
  future work (see `docs/architecture/model-management-foundation.md`).
- **Retention Policy admin UI ships without any enforcement scheduler**
  — explicit, documented: automated cleanup is Phase 11 scope, this
  phase manages policy definitions only.
- **No frontend unit tests for the ~20 new admin pages** — verified via
  `tsc`/eslint/`vite build` passing, a real Docker Compose browser
  walkthrough, and manual code review, matching Phase 4/5/6's identical,
  explicitly disclosed gap for their own new frontend surfaces.
- **Dictionaries not implemented, not even a placeholder** — deliberately
  deferred per the roadmap §73 boundary (appears only in the spec's
  illustrative mockup, not the phase's actual scope list).
- **No true from-a-tagged-Phase-6-checkout upgrade rehearsal** — this
  phase's upgrade path (no schema change) was instead validated by
  actually running the RBAC reseed CLI against a live stack (see
  "Phase-6 Upgrade Validation" above), which directly exercises the one
  real risk (seed idempotency) rather than needing a full prior-version
  checkout.

## Open Risks

None new this phase. The Ollama container's accepted CRITICAL finding
from Phase 4 (`compliance/container-inventory.yml`'s `ollama/ollama`
entry) remains open and tracked exactly as Phase 4-6 left it — this phase
did not touch the LLM provider or its container.

## Architecture Deviations

None from the phase brief's explicit scope. No new ADR was added this
phase — there was no genuine, irreversible architecture decision to
record (unlike, e.g., Phase 6's dynamic-schema ADR-0028); every design
choice here (permission reuse, no new tables, deriving Workers status
from existing `ProcessingJob` rows rather than a new registry) follows
directly from precedents already established and documented in prior
phases' ADRs.

## Deferred Items

See `docs/architecture/future-considerations.md`'s new "Phase 7
additions": Dictionaries; Evaluation Lab/Longitudinal Documentation/
Service Accounts/Webhooks/Backups/GPU-metrics dashboard (later-phase
roadmap items, per the mockup vs. roadmap distinction); automated
Retention Cleanup; a real `SpeechProfile`/`DiarizationProfile` entity;
Storage scan scalability; the About page's container-image gap; nav
customization/per-role dashboards.

## Git / PR / Merge Status

- Branch: `phase-7-administration`, off `main` at `b407484`.
- PR: [#12](https://github.com/ley338-gif/VocaDox/pull/12) — "Phase 7:
  Administration — Admin Portal (Users/Groups/Orgs/Jobs/Workers/Storage/
  Retention/Audit/About)".
- Commits: `6c46a3e` (backend admin API), `350904a` (frontend Admin
  Portal shell + pages), `872dcb2` (documentation).
- All 7 required GitHub Actions checks: **green** on both workflow runs
  for the final commit (`872dcb2`).
- **Merge: performed** (`85d658d`, regular merge commit on `main`,
  matching Phase 5/6's precedent). Verified `main` fast-forwarded to
  `85d658d` locally after merge. No open risk required product-owner
  escalation this phase — every merge-gate condition in the phase brief
  was independently verified: the full Admin Portal navigation structure
  exists and is functional with real data on every page (verified live,
  not just unit tests); Dashboard shows real health/status with no
  fabricated "Healthy" states and no conversation-content leakage
  (verified by response-schema inspection and exact-key-set test);
  Users/Groups/Organizations admin CRUD works end-to-end through the
  real API (verified live in the browser, not just curl); Retention
  policy admin UI works against the real data model; Audit viewer
  correctly shows real accumulated events without exposing prohibited
  content; admin-portal access is properly permission-gated (12
  dedicated 403 tests plus live non-admin-user verification, matching
  the rigor of every prior phase's authorization testing); no regression
  in Phases 0-6 (211/211 tests, including all 184 pre-existing; 21/21
  frontend); fresh install/restart persistence were validated against
  real infrastructure; the Phase 6→7 upgrade path was validated against
  a real running stack; 0 blocked/0 unknown licenses; all CI green; and
  documentation is current.

## Recommendation

**GO for Phase 8.** The Admin Portal is genuinely functional end-to-end
over real data, with no regression to any prior phase's functionality.
Every roadmap §73 Phase 7 item has a working, permission-gated page
backed by a real endpoint over real data — verified not just by the
automated test suite but by an actual browser session against a live
Docker Compose deployment, including deliberately exercising the
non-admin-denial path with a freshly-created user. Two real, pre-existing
gaps flagged by prior phases (`POST /organizations`, the Processing
Profile speech/diarization config UI) were closed as part of this
phase's natural scope, and every deliberately-deferred item (Dictionaries,
Evaluation Lab, Service Accounts, automated Retention Cleanup, a real
SpeechProfile/DiarizationProfile entity) is explicitly documented rather
than silently skipped. No new open risk was introduced; the dependency
set is completely unchanged, so license compliance carries zero new
exposure this phase.
