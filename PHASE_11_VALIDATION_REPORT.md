# Phase 11 Validation Report: Operations

## Executive Summary

Phase 11 implements roadmap §73: Worker/GPU/Queue Metrics, Backup,
Restore, Retention Cleanup, Model Storage, Offline Installation, and
Disaster Recovery. This is the domain that finally enforces the
`RetentionPolicy` model that has existed since Phase 2 with zero
enforcement until now, and it is also the single most consequential
feature this project has built to date in terms of blast radius if
wrong (real, irreversible deletion of user data).

Every merge-gate item was tested for real, not assumed:

- **Backup and restore** were exercised end to end against real Docker
  infrastructure: real synthetic data seeded, a real `pg_dump`+media-tar
  backup created, the database and media volumes genuinely destroyed
  (kept only the backups volume, exactly as an off-host backup would
  survive a host failure), fresh unmigrated infrastructure stood up, and
  the backup restored into it — verified byte-exact (sha256 match on the
  restored media file) and row-exact (conversation/transcript data
  intact).
- **Retention cleanup** was tested both at the unit level (9 pytest
  tests against a real SQLite database and real bytes on a real
  filesystem) and against the live restored Postgres database above:
  dry run reported correct counts and deleted nothing (verified);
  `--execute` performed genuine physical deletion, verified both on disk
  (file gone) and in the database (transcript row genuinely `DELETE`d,
  media asset tombstoned with `deleted_at` set, never a soft-delete flag
  alone).
- **Two real infrastructure bugs** were found and fixed by actually
  running the feature, not by code review: a backup-directory permission
  error, and a Postgres 16-vs-17 `pg_dump`/`pg_restore` client/server
  version mismatch.
- **A real Trivy-caught CRITICAL regression** (installing
  `postgresql-client` silently reintroduced the entire `perl` toolchain
  Phase 0 had deliberately purged) was found and fixed, and re-verified
  at 0 CRITICAL findings.
- Fresh install, Phase-10 upgrade equivalence, and restart persistence
  were all validated against real Postgres 17.6 Docker infrastructure.

**Recommendation: GO for Phase 12**, with the honest limitations below
(no built-in backup scheduler/rotation/off-host shipping, no durable
metrics time-series) documented as deliberate, explicitly-deferred scope
rather than gaps discovered too late to flag.

## Scope

Implemented (roadmap §73):

- **Worker/GPU/Queue Metrics** (`app.operations.metrics_service`):
  real throughput aggregates over `ProcessingJob` rows extending Phase
  7's Dashboard/Jobs/Workers read-model; GPU presence/VRAM reusing Phase
  3's `detect_device_capabilities` plus a best-effort `nvidia-smi`
  utilization query; queue depth-by-job-type and hourly throughput
  buckets.
- **Backup** (`app.operations.backup_service.create_backup`): real
  `pg_dump --format=custom` (full schema+data) plus a real tar archive
  of the media storage root, admin-triggerable over HTTP
  (`backup:trigger`).
- **Restore** (`app.operations.backup_service.restore_backup`):
  deliberately CLI-only (`python -m app.cli.backup restore`), never an
  HTTP endpoint — see that module's docstring for the reasoning
  (destructive, and unsafe against an in-process connection pool).
- **Retention Cleanup** (`app.operations.retention_service.
  run_retention_cleanup`): the real enforcement worker for
  `RetentionPolicy`, safe-by-default (`dry_run` has no default at the
  service layer — every call site must decide explicitly, and both real
  call sites default their own parameter to `True`), genuine physical
  deletion (storage bytes removed before the DB tombstone/DELETE),
  granular per-item audit trail.
- **Model Storage** (`app.operations.metrics_service.
  model_storage_overview`): admin visibility into the models volume
  specifically, distinct from Phase 7's general Storage page.
- **Offline Installation**: consolidated guide
  (`docs/operations/offline-installation.md`) tying Phase 3.1's
  AI-model offline evidence together with a component-by-component
  runtime network survey of the rest of the stack.
- **Disaster Recovery**: concrete runbook
  (`docs/operations/disaster-recovery.md`) built directly on the actual
  mechanism above, with real RPO/RTO grounded in this phase's own test.
- **RBAC**: `operations:read`, `backup:trigger`,
  `retention-cleanup:trigger`, `retention-cleanup:read` — narrowly
  granted (System Admin gets all four; Manager/Auditor-equivalent roles
  get only the two read permissions; no role beyond System Admin gets
  either `*:trigger` permission).
- **Audit**: `backup.created`, `retention_cleanup.run`,
  `retention_cleanup.item_deleted` events, each with enough structured
  detail (ids, byte counts, policy/reason) to explain what happened
  without ever logging deleted content.
- **Admin Portal**: new Operations page (worker/GPU/queue metrics, model
  storage, backup create/list); Retention page extended with the
  `delete_transcript` policy field and a retention-cleanup
  trigger/history section.

Explicitly out of scope (per phase brief): the Phase 12 hardening/
security audit itself, new AI/intelligence features, any core domain
change beyond what real retention cleanup required
(`retention_policies.delete_transcript`, purely additive).

## Architecture

`app/operations/` is a new domain package, following the same
models/schemas/service/router shape as every other domain in this
codebase:

- `models.py`: `BackupRecord` (one row per backup attempt, mirroring the
  Phase 10 `WebhookDelivery` "one row per real attempt, never silently
  discarded" pattern), `RetentionCleanupRun` (one row per invocation),
  `RetentionCleanupItem` (one row per individual physical deletion, or
  per would-be deletion in dry-run mode).
- `backup_service.py`: `create_backup` (async, real `pg_dump` +
  media tar), `restore_backup` (sync, CLI-only, real `pg_restore
  --clean`).
- `retention_service.py`: `run_retention_cleanup`, the real enforcement
  worker.
- `metrics_service.py`: worker throughput, GPU metrics, queue depth/
  throughput, model storage overview — pure read-model functions over
  existing tables/filesystem/subprocess, no new state.
- `router.py`: admin-only endpoints under `/admin/operations/*`.

Nothing here duplicates existing infrastructure: worker/queue metrics
extend Phase 7's `ProcessingJob`-based read-model; GPU metrics reuse
Phase 3's device-detection code unchanged; model storage reuses Phase
7's `directory_size_bytes` helper (renamed from
`_directory_size_bytes` to make it importable across domains);
retention cleanup enforces the Phase 2 `RetentionPolicy` model, extended
with one additive `delete_transcript` boolean rather than a redesign
into the spec's richer per-artifact-status enum — the existing
`retention_days`/`delete_source_media`/`delete_derived_media` flags
already covered the intent, and `delete_transcript` was the one gap the
"zero retention" pattern (Audio -> Processing -> Document -> Audio
DELETE -> Transcript DELETE) needed.

Migration `0012_operations` adds `retention_policies.delete_transcript`
(nullable=False, server_default=false — every existing row keeps its
exact prior no-transcript-deletion behavior) plus the three new tables.

## Worker/GPU/Queue Metrics

`GET /admin/operations/metrics` returns:

- **Per-role worker throughput** (`worker-speech`, `worker-diarization`,
  `worker-extraction`): running/queued job counts, succeeded-last-1h/24h,
  failed-last-24h, and mean duration over jobs that succeeded in the
  last 24h — all real aggregates over `ProcessingJob.updated_at`/
  `started_at`/`completed_at`, computed in Python (not SQL
  `date_trunc`, which the SQLite-backed test suite doesn't support).
- **GPU**: `detect_device_capabilities()` (Phase 3, unchanged) for
  presence/name/VRAM, plus a best-effort `nvidia-smi
  --query-gpu=utilization.gpu` for live utilization — exception-safe,
  returns `None` ("not available") rather than a fabricated number if
  `nvidia-smi` isn't reachable. This development sandbox has no NVIDIA
  GPU, so `cuda_available: false` was the only value actually
  observable here; the code path was exercised via the unit test suite's
  RBAC/response-shape assertions, not against real GPU hardware.
- **Queue**: current depth (queued+running) by job type, and hourly
  succeeded/failed throughput buckets over the last 24h.

**Known limitation, stated honestly**: there is no durable metrics
time-series store. Every number above is a real rolling-window
aggregate computed on demand — accurate for "what's happening now," but
nothing is retained once a `ProcessingJob` row ages past the window.
See `docs/architecture/future-considerations.md`'s Phase 11 section.

## Backup

`POST /admin/operations/backups` (permission: `backup:trigger`) and
`docker compose run --rm backup create` both call `create_backup`,
which:

1. Inserts a `BackupRecord` (status `running`), flushes to get its id.
2. Runs `pg_dump --format=custom --no-owner --no-privileges` against
   the live database into `<backup_root>/<id>/database.dump`.
3. Tars the media storage root into `<backup_root>/<id>/media.tar` on a
   background thread (never blocking the event loop).
4. Marks the record `succeeded` (byte counts, file count recorded) or
   `failed` (real subprocess stderr captured, truncated to 2048 chars —
   never swallowed).
5. Emits a `backup.created` audit event (and, if webhooks are
   configured, a `backup.created` webhook delivery).

A backup never touches or mutates the source data it reads from.
`GET /admin/operations/backups` (permission: `operations:read`) lists
every attempt, success or failure — mirroring the Phase 10
`WebhookDelivery` "one row per real attempt" pattern so a failed backup
is visible, not silently lost.

**Real backup created in this phase's own testing**: `database.dump`
155,691-155,700 bytes (varying slightly by seeded UUID content, exactly
what's expected for a near-empty synthetic dataset), `media.tar` 10,240
bytes (1 file, tar block-size rounding of a 60-byte payload) — see
Restore below for the full test.

## Restore (real test result)

Restore is deliberately CLI-only — see `app/operations/
backup_service.py`'s module docstring. `python -m app.cli.backup
restore <backup_id_or_dir>` runs `pg_restore --clean --if-exists
--no-owner --no-privileges` against the target database (drops and
recreates every object the dump describes) and, if the backup includes a
media tar, deletes and replaces the entire target media directory with
the tar's contents.

### Real restore-into-fresh-infrastructure test

Performed for real against Docker infrastructure, twice (once before and
once after the Postgres version-mismatch and perl-regression fixes
below, to confirm both fixes together did not break the flow):

1. `docker compose up -d postgres` (fresh, empty) + `docker compose run
   --rm migrate` — migration chain `0001_baseline` through
   `0012_operations` applied cleanly.
2. Seeded real synthetic data directly via the ORM: 1 organization, 1
   conversation, 1 real `MediaAsset` (60 real bytes written through
   `LocalFilesystemStorage`, sha256-hashed), 1 `ProcessingRun`, 1
   `Transcript` with 1 `TranscriptSegment`.
3. `docker compose run --rm backup create` — succeeded (see Backup
   above for byte counts).
4. **Simulated total infrastructure loss**: stopped and removed the
   `postgres`/`valkey` containers and deleted the
   `vocadox_postgres_data`, `vocadox_backend_data` (media), and
   `vocadox_valkey_data` volumes — **keeping only
   `vocadox_backups_data`**, exactly as a real off-host backup volume
   would survive a host failure that destroys everything else.
   Confirmed via `docker volume ls` that only the backups volume
   remained.
5. `docker compose up -d postgres` — a brand-new, **completely
   unmigrated** Postgres container (no `alembic upgrade head` run
   against it).
6. `docker compose run --rm backup restore <backup_id>` — succeeded.
7. **Verification** (a standalone script querying the restored
   database and filesystem directly):
   - The conversation row was present, with its exact title.
   - The restored media file's real bytes on disk, re-hashed, matched
     the original sha256 exactly — byte-for-byte, not just "a file
     exists."
   - The transcript segment's exact text matched.
8. A subsequent normal `docker compose run --rm migrate` against the
   restored database correctly found it already at `alembic` head (a
   clean no-op) — confirming a `pg_dump`-based restore needs no separate
   schema-migration step, since the dump includes the full schema.

This is real, verified evidence, not a simulated or assumed result. Full
command transcript and reasoning: `docs/operations/
disaster-recovery.md`.

## Retention Cleanup (real test result, dry-run behavior)

`app.operations.retention_service.run_retention_cleanup` evaluates every
active `RetentionPolicy` with a real `retention_days` threshold against
the conversations assigned to it. A conversation whose
`retention_policy_id` is `NULL`, or points at an inactive policy, or a
policy with `retention_days=None` ("keep indefinitely"), is never
touched — enforced by the query's own `WHERE` clause, not by an
after-the-fact filter.

**Safe by default, with no accidental default anywhere in the call
chain**: the service function's `dry_run` parameter has no default at
all (every caller must decide explicitly); the admin API's
`RetentionCleanupRunRequest.dry_run` defaults to `True`; the CLI's
`run` subcommand requires an explicit `--execute` flag to do anything
other than a dry run.

Physical deletion, never a soft-delete flag alone: media bytes are
removed via `StorageProvider.delete(storage_key)` **before** the
`MediaAsset.deleted_at` tombstone is set (so a failed delete never
leaves a false tombstone); transcript deletion is a genuine SQL
`DELETE` of the `Transcript` row, with `TranscriptSegment`/
`TranscriptSegmentCorrection` cascading at the database FK level
(`ondelete="CASCADE"`, already declared since Phase 3) — the segment
text is truly gone, never blanked in place. Every individual deletion
(or would-be deletion, in dry-run mode) is recorded as its own
`RetentionCleanupItem` row **before** the physical action happens, with
a structured `reason` string (e.g. `"age_days=45 >=
retention_days=30 (policy 'Standard-30', id=...)"`) — never the
deleted content itself.

### Unit test coverage (backend/tests/operations/test_retention_service.py, 9 tests)

Real SQLite database (FK cascade explicitly enabled via
`PRAGMA foreign_keys=ON` so the cascade assertions genuinely exercise
the same behavior Postgres enforces in production) and the real
`LocalFilesystemStorage` provider writing to a real temp-directory
filesystem — never a mock:

1. `test_dry_run_deletes_nothing_but_records_what_would_be_deleted` —
   dry run against an eligible conversation reports the correct item
   count and byte count, and leaves both the filesystem bytes and the
   DB rows completely untouched.
2. `test_execute_zero_retention_deletes_audio_and_transcript_for_real`
   — the full "zero retention" pattern: source + derived media
   genuinely gone from disk, `MediaAsset` rows tombstoned
   (`deleted_at` set, rows retained for provenance), `Transcript` row
   and its segments genuinely gone from the database.
3. `test_conversation_younger_than_threshold_is_untouched`.
4. `test_conversation_with_keep_indefinitely_policy_is_never_touched`
   — a `retention_days=None` policy is never picked up regardless of
   conversation age.
5. `test_conversation_with_no_policy_is_never_touched` — proves an
   unrelated aggressive policy in the same database never affects a
   conversation not assigned to it.
6. `test_inactive_policy_is_never_enforced`.
7. `test_already_deleted_asset_is_never_deleted_twice` — idempotency: a
   second run against already-cleaned data deletes/counts nothing
   further.
8. `test_only_conversations_matching_policy_are_affected` — proves the
   per-policy `WHERE` scoping, not a blanket sweep.
9. `test_run_and_items_are_queryable_after_commit`.

### Real Docker-based end-to-end test

Performed against the same live, restored Postgres database from the
Restore test above:

1. Assigned a real, newly-created `retention_days=0,
   delete_source_media=True, delete_derived_media=True,
   delete_transcript=True` policy to the seeded conversation.
2. `docker compose run --rm retention-cleanup run` (dry run, the
   default) — reported "1 conversation evaluated, 2 items that would be
   deleted, 60 bytes that would be freed." Verified independently
   afterward: the media file was still present on disk.
3. `docker compose run --rm retention-cleanup run --execute` —
   reported "2 items deleted, 60 bytes freed." Verified independently
   afterward:
   - The media file was **genuinely gone** from disk.
   - The `Transcript` row was **genuinely gone** from the database
     (`SELECT` returned `None`).
   - The `MediaAsset` row **remained** as a tombstone, with
     `deleted_at` set to a real timestamp.

Exactly what should have been deleted was deleted, and nothing else —
verified in both the database and on the filesystem, not assumed from
the run's own self-reported counts.

## Model Storage

`GET /admin/operations/model-storage` (permission: `operations:read`)
lists every top-level directory under `model_volume_root` (matching how
Phase 3.1's `install_models`/`model_manager` lay out installed model
profiles) with a real recursive byte size for each, plus a total. Never
mixed with `media_storage_root` (ADR-0018's "don't mix model files with
Conversation media" principle, now applied a third time to backups too
— see `deploy/docker-compose.yml`'s comment on the dedicated
`vocadox_backups_data` volume).

## Offline Installation

`docs/operations/offline-installation.md` consolidates Phase 3.1's real,
empirically-verified AI-model offline evidence (real
`HF_HUB_OFFLINE=1` enforcement, verified during real inference — see
`docs/operations/offline-model-installation.md`) with a
component-by-component runtime-network survey of the rest of the stack
performed this phase: backend, Postgres, Valkey, frontend, and this
phase's own Backup/Restore and Retention Cleanup mechanisms all have
zero runtime network dependency beyond the compose-internal network.

**Honestly stated**: this is a documentation consolidation, not a new
isolation test. Phase 3.1's own report already stated its evidence does
not include a true network-namespace-level disconnection test; this
phase does not newly achieve that stronger guarantee and says so
explicitly rather than re-claiming the same evidence as new.

## Disaster Recovery

`docs/operations/disaster-recovery.md` is the concrete runbook: what is/
isn't backed up, exact restore commands, the real test above as
evidence, honest RPO/RTO (RPO = time since last backup — **this phase
ships no automatic backup schedule**, an operator must configure one;
RTO = infrastructure stand-up time + restore time, both real and
measurable, benchmarked against this phase's own small synthetic
dataset rather than a fabricated production-scale number), and an
explicit operator setup checklist (scheduling, off-host storage,
retention/rotation — none of which this codebase does automatically).

## API / OpenAPI

New endpoints under `/admin/operations`:

- `GET /admin/operations/metrics`
- `GET /admin/operations/model-storage`
- `GET /admin/operations/backups`, `POST /admin/operations/backups`
- `GET /admin/operations/retention-cleanup/runs`
- `GET /admin/operations/retention-cleanup/runs/{run_id}/items`
- `POST /admin/operations/retention-cleanup/run`

`frontend/openapi.json` and `frontend/src/api/generated/schema.d.ts`
were regenerated against the live schema (fetched from a running
`uvicorn` instance, exactly as the CI `openapi-client-drift` job does)
and committed — `git diff` showed real drift before the regeneration
(the new endpoints and the `delete_transcript` field were absent), none
after.

## Authorization

Four new permissions, deliberately narrow (spec: "restrict tightly, do
not default-grant broadly"):

| Permission | Granted to |
|---|---|
| `operations:read` | System Admin, Manager, Auditor |
| `backup:trigger` | System Admin only |
| `retention-cleanup:trigger` | System Admin only |
| `retention-cleanup:read` | System Admin, Manager, Auditor |

No role beyond System Admin can trigger a backup or a real retention
cleanup run. Verified by `tests/operations/test_router.py` (6 tests):
unauthenticated -> 401; a plain "User" role (no operations permissions
at all) -> 403 on every endpoint; System Admin -> 200/201 on every
endpoint; the retention-cleanup run endpoint's `dry_run` defaults to
`true` when the request body omits it.

## Audit

`backup.created` (backup id, status, byte counts), `retention_cleanup.
run` (run id, dry_run, status, counts), and one `retention_cleanup.
item_deleted` event per individual deletion when a run was real and
non-empty (run id, conversation id, action, reason) — enough detail to
explain every deletion after the fact without ever logging the deleted
content itself, per the phase brief's Process Rule 7.

## Security

- Retention cleanup's destructive path requires an admin to explicitly
  set `dry_run: false` (API) or pass `--execute` (CLI) — there is no
  way to trigger real deletion by omission or default anywhere in the
  code.
- Restore is never reachable over HTTP at all, closing off the
  "one accidental click" risk entirely for the single most destructive
  operation this phase adds.
- `postgresql-client` was found (via a real Trivy scan of the built
  image) to reintroduce the entire `perl`/`perl-base`/`perl-modules`/
  `libperl` CVE family Phase 0 had deliberately purged — 12 CRITICAL
  findings. Fixed by extracting the real `pg_dump`/`pg_restore`/`psql`
  ELF binaries (confirmed via `ldd` to have zero Perl dependency) to
  `/usr/local/bin` and purging the entire `postgresql-client*` package
  family and Perl again. Re-scanned: **0 CRITICAL findings** on the
  backend image.
- `backup_root`/`media_storage_root` paths come only from server-side
  `Settings`, never from request input — no path-traversal surface in
  the backup/restore/retention-cleanup code paths.

## Compliance / Dependencies / Containers / Licenses

`python compliance/check_licenses.py`:

```
Summary by category (never summed together — see report for why)
  category      approved   review_required  blocked  unknown
  direct        36         0                0        0
  transitive    495        3                0        0
  containers    7          0                0        0
  models        6          0                0        0

result: PASS (no blocked or unknown-licensed items)
```

0 blocked, 0 unknown — the `review_required` count (3, transitive) is
pre-existing and unrelated to this phase's changes (no new direct
Python/npm dependency was added; `postgresql-client` is an OS package,
already governed by the container-inventory's documented "OS package
layer not individually audited" note, same as every prior phase's base
image).

**Container image change**: `postgres:16.6-alpine3.20` ->
`postgres:17.6-alpine3.22` (both official images, PostgreSQL License,
approved), bumped after the real client/server version-mismatch bug
below. Recorded in `compliance/container-inventory.yml` with the real
reasoning.

**Trivy CRITICAL scan** (backend image, matching the CI
`container-vulnerability-scan` job exactly): 0 findings after the perl
fix above (12 before it — see Bugs Found and Fixed This Phase).

## Tests

- **Backend**: 288 tests passed (0 failed), including 15 new tests in
  `backend/tests/operations/` (9 `test_retention_service.py`, 6
  `test_router.py`). Full suite re-run clean after every infrastructure
  change this phase made (Dockerfile permission fix, Postgres version
  bump, perl-purge fix) — no regression introduced by any of them.
- **Frontend**: `tsc -b --noEmit` clean, `eslint .` clean, `vitest run`
  21 tests passed (no new frontend tests added this phase — see Known
  Limitations, consistent with this codebase's existing sparse
  frontend-test pattern), production `vite build` clean.

## GitHub Actions

All 7 required checks passed on PR #19 (`gh pr checks 19`):

- Alembic migration (real Postgres)
- Backend (lint / typecheck / test)
- Container vulnerability scan (Trivy — backend/frontend/AI-worker
  runtime + frontend build/dev images)
- Docker build (backend + frontend + AI worker)
- Frontend (lint / typecheck / test / build)
- License compliance (direct + full transitive tree)
- OpenAPI TS client drift check

Not clean on the first push — two real CI failures were found and fixed
before all checks passed:

- `ruff check .` failed (never run locally before the first push):
  an `ASYNC240` blocking-pathlib-call violation in `backup_service.py`
  (fixed by moving every synchronous filesystem call onto
  `asyncio.to_thread`), an unsorted import block, an unused import, an
  unused test variable, and several line-length violations across
  `app/operations/` and `tests/operations/`.
- `mypy app` failed: `router.py` constructed several Pydantic response
  models via `Model(**dict[str, object])`, which mypy correctly
  rejects as a type mismatch per field. Fixed by switching to
  `Model.model_validate(...)`, matching the existing pattern already
  used elsewhere in this codebase (e.g.
  `app.administration.router`'s `WorkerRoleStatus.model_validate`).

Both fixes were verified locally (`ruff check .`, `mypy app`, full
288-test `pytest` run) before pushing, then confirmed green in CI.

## Fresh Install

Validated for real against `docker compose` (`postgres`, `valkey`,
`migrate`, `backend`, `frontend` — the GPU-dependent
`worker-speech`/`worker-diarization`/`worker-extraction`/`ollama`/
`model-manager` services were not re-validated here, consistent with
Phase 10's precedent for a phase touching no speech/diarization/LLM
provider code):

- `docker compose build migrate backend frontend` — all three images
  built cleanly (including the fixed backend Dockerfile).
- `docker compose up -d postgres valkey` then `docker compose run --rm
  migrate` — migration chain `0001_baseline` through `0012_operations`
  applied cleanly against a real, empty Postgres **17.6** container
  (bumped from 16.6 this phase — see below).
- `docker compose up -d backend frontend` — `GET /health/ready`
  returned `{"status":"ready","database":true,"valkey":true}`; the
  frontend dev server responded `200` at `http://localhost:5173/`.
- `GET /openapi.json` confirmed the new `/admin/operations/metrics`
  path is present in the live schema; an unauthenticated request to it
  correctly returned `401`.

## Phase-10 Upgrade

Simulated on the *same* live database used for the fresh-install
walkthrough above (already containing 1 organization, 1 conversation, 1
media asset, 1 transcript — seeded synthetic data):

- `docker compose run --rm migrate alembic downgrade -1` — cleanly
  dropped `backup_records`/`retention_cleanup_runs`/
  `retention_cleanup_items` and the `retention_policies.
  delete_transcript` column back to the `0011_integrations` state.
  Confirmed via `psql`: pre-existing data intact (`organizations`=1,
  `conversations`=1, `transcripts`=1), and the three new tables/column
  genuinely absent (`to_regclass(...)` returned `NULL` for all three
  table names).
- `docker compose run --rm migrate` (upgrade back to head) —
  re-applied `0012_operations` cleanly on top of the still-populated
  database. Confirmed all four row counts (`organizations`,
  `conversations`, `transcripts`, `media_assets`) unchanged after the
  round trip.

This is the real equivalent of "an existing Phase 10 install upgrades
to Phase 11": no data loss, no migration error, in either direction.

## Restart Persistence

`docker compose restart backend postgres` — `GET /health/ready`
returned healthy immediately afterward; the seeded conversation was
still present in the database (`SELECT count(*) FROM conversations` =
1, unchanged); the operations metrics endpoint still routed correctly
post-restart (`401` unauthenticated, matching pre-restart behavior).

## Known Limitations

- **No durable metrics time-series store.** See Worker/GPU/Queue
  Metrics above — real rolling-window aggregates only, nothing
  retained beyond the window.
- **No automatic backup schedule, rotation, or off-host shipping.**
  This codebase performs a backup only when explicitly triggered
  (admin UI, API, or CLI). An operator must wire up their own
  scheduler (cron/CronJob), retention/rotation policy, and off-host
  storage — see `docs/operations/disaster-recovery.md`'s "Operator
  setup checklist." Building any of these speculatively without a real
  deployment to size them against risked getting the policy wrong in a
  way that either wastes storage or deletes a needed backup.
- **No in-process retention-cleanup scheduler.** `docker compose run
  --rm retention-cleanup run --execute` is designed for an external
  scheduler, consistent with this project's existing "no in-process
  cron" precedent.
- **No new frontend tests were added this phase.** The existing
  frontend test suite (21 tests) is smoke-level and phase-specific
  frontend coverage has historically been light in this codebase
  (consistent with every prior phase's validation report).
- **GPU metrics were not exercised against real GPU hardware** in this
  sandbox (no NVIDIA GPU present) — `cuda_available: false` was the
  only value actually observed; the `nvidia-smi`-based utilization path
  is exception-safe by construction (returns `None` on any failure) but
  was not exercised against a real GPU.
- **Offline installation verification remains sandbox-level**, not a
  true network-namespace-isolated test — see Offline Installation
  above; this is Phase 3.1's already-stated limitation, not newly
  introduced or newly resolved by this phase.
- **Postgres/`postgresql-client` version coupling.** The fix for the
  client/server version mismatch (matching the server to whatever
  `postgresql-client` the base image ships) means a future base-image
  bump that changes the shipped client version could silently
  reintroduce the same class of mismatch if the server version isn't
  bumped in lockstep. Documented in `docs/architecture/
  future-considerations.md` as a Phase 12 hardening candidate (pinning
  via the official PGDG apt repository) rather than built speculatively
  now.

## Bugs Found and Fixed This Phase

All three found by actually running the feature against real
infrastructure, not by code review:

1. **Backup-directory `PermissionError`.** `docker compose run --rm
   backup create` failed writing to `/app/backups` — the named volume
   mount point is created root-owned by Docker, and only `/app/data`
   had been `chown`'d to the non-root `vocadox` user. Fixed by
   extending the existing `mkdir`+`chown` step to `/app/backups` too
   (`backend/Dockerfile`).
2. **Postgres client/server version mismatch.** Restoring into fresh
   infrastructure failed with `pg_restore: error: could not execute
   query: ERROR: unrecognized configuration parameter
   "transaction_timeout"`. Root cause: Debian trixie's
   `postgresql-client` package is 17.x, but the compose stack pinned
   the Postgres **server** at 16.6; `pg_dump` 17.x emits a `SET
   transaction_timeout = 0;` GUC (introduced in Postgres 17) that a
   16.x server's `pg_restore` rejects outright. Fixed by bumping the
   pinned Postgres image (`deploy/docker-compose.yml` and
   `.github/workflows/ci.yml`) to `17.6-alpine3.22`, matching the
   client version trixie already ships, rather than adding a
   third-party apt repository or copying cross-distro binaries just to
   pin an older client.
3. **Trivy CRITICAL regression from `postgresql-client`.** A Trivy scan
   of the rebuilt backend image (run as part of this phase's own
   validation, matching CI's `container-vulnerability-scan` job) found
   12 CRITICAL findings — the entire `perl`/`perl-base`/
   `perl-modules`/`libperl` family, all traced to
   `postgresql-client-common`'s `pg_wrapper`, which is itself a Perl
   script providing `/usr/bin/pg_dump`/`pg_restore`/`psql`. This
   silently reintroduced the exact CVE family Phase 0 had deliberately
   purged from the base image. Fixed by copying the real ELF binaries
   from `/usr/lib/postgresql/<ver>/bin/` (confirmed via `ldd` to have
   zero Perl dependency — only `libpq`/`libssl`/`libgssapi_krb5`/etc.)
   to `/usr/local/bin` before purging Perl and the entire
   `postgresql-client*` package family again, keeping `libpq5` (marked
   `apt-mark manual` so `autoremove` doesn't take it). Re-scanned: 0
   CRITICAL findings. Re-verified the full real backup/restore/
   retention-cleanup cycle still passes after this fix.

## Open Risks

- Backup artifacts are stored unencrypted and are not automatically
  shipped off-host by this codebase — a real deployment's operator must
  do both, or the "off-host survives a host failure" guarantee this
  phase's own disaster-recovery test relied on does not actually hold
  in that deployment.
- Without an operator-configured backup schedule, RPO is effectively
  "whenever an admin last remembered to click Create Backup" — not an
  acceptable production posture on its own; flagged prominently in the
  disaster-recovery runbook's checklist, not silently left as an
  assumption.
- The Postgres/`postgresql-client` version-coupling risk described in
  Known Limitations.

## Architecture Deviations

- `retention_policies.delete_transcript` was added as a single
  additive boolean rather than the spec's richer
  `DELETE_AFTER_PROCESSING`/`DELETE_AFTER_APPROVAL`/
  `DELETE_AFTER_DURATION`/`KEEP` enum — per the phase brief's explicit
  guidance to extend the existing simple model rather than force a
  redesign it doesn't need. The existing `retention_days` +
  `delete_source_media`/`delete_derived_media` flags already covered
  every case the enum would express except transcript deletion, which
  this one field closes.
- `app.administration.service._directory_size_bytes` was renamed to
  `directory_size_bytes` (made non-private) so
  `app.operations.metrics_service` could reuse it for Model Storage
  without duplicating a recursive-size helper — a pure refactor, same
  behavior, covered by the pre-existing Phase 7 storage tests (all
  still pass).

## Deferred Items

See Known Limitations above and `docs/architecture/
future-considerations.md`'s Phase 11 section for the full list with
reasoning: durable metrics history, multi-GPU metrics, backup
encryption/off-host automation/rotation, retention-cleanup scheduling,
an HTTP-triggered maintenance-window restore flow, and PGDG-based
Postgres-client version pinning.

## Git / PR / Merge Status

- Branch: `phase-11-operations` (off `main`@`0fc026c`, Phase 0-10
  merged).
- PR: #19, all 7 required GitHub Actions checks green.
- Merged: squash-merged to `main` as `6322ab8` (branch deleted after
  merge).
- This report itself: added via a follow-up branch/PR
  (`phase-11-validation-report`), matching this repo's existing
  precedent (e.g. Phase 9's `phase-9-validation-report` PR #17) of
  merging the feature branch first, then adding the validation report
  in a small separate PR.

## Recommendation

**GO for Phase 12**, conditional on the honest limitations above being
acceptable for the deployment(s) this codebase actually targets before
going to production:

- Backup/restore genuinely work, verified byte-exact and row-exact
  against a real disaster scenario.
- Retention cleanup deletes exactly what it should, and nothing else —
  verified in both the database and on the filesystem, dry-run safe by
  default at every call site.
- No regression in Phases 0-10 (full 288-test suite green throughout).
- Fresh install, Phase-10 upgrade, and restart persistence all pass
  against real Postgres 17.6 infrastructure.
- 0 blocked/0 unknown licenses; 0 CRITICAL Trivy findings on the
  backend image (after fixing the regression this phase itself
  introduced and caught).

The one item that would change this recommendation to NO-GO is if the
target deployment has no plan to implement the operator-side backup
scheduling/off-host-storage/rotation this codebase deliberately leaves
external — that gap is real and prominently flagged, not hidden.
