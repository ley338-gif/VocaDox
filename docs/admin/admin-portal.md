# Admin Portal (Phase 7)

The Admin Portal lives at `/admin` in the frontend, organized into the
exact section groups the product spec's mockup shows (spec §48):

```
Dashboard
MANAGEMENT: Users, Groups, Organizations, Templates
AI: Models, Speech, Diarization, Processing Profiles, Prompts
OPERATIONS: Jobs, Workers, Storage, Retention
SECURITY: Authentication, Audit
SYSTEM: About & Licenses
```

`frontend/src/components/AdminLayout.tsx` renders this sidebar; each link
is hidden unless the current user has that section's permission, but the
sidebar is a convenience only — every page is independently wrapped in
`RequirePermission` (`frontend/src/App.tsx`) matching exactly the
permission its backend endpoint enforces via `app.identity.deps
.require_permission`. There is no single blanket "admin" gate beyond
`system:admin` for the Dashboard/Jobs/Workers/Storage/Authentication/About
pages — every other page uses the narrower, pre-existing permission that
already scoped that resource (e.g. `user:manage`, `audit:read`,
`template:read`).

**Explicitly out of scope this phase** (see
`docs/architecture/future-considerations.md`): Dictionaries, Evaluation
Lab, Service Accounts/API/Webhooks, Backups, and any automated Retention
Cleanup worker.

## Section-by-section reference

| Section | Permission | Backend | Notes |
|---|---|---|---|
| Dashboard | `system:admin` | `GET /admin/dashboard` | Real component health (API/Postgres/Valkey/Speech/Diarization/LLM), real queue counts, narrow hardware snapshot. Never renders conversation content — the response schema structurally cannot carry any. |
| Users | `user:manage` | `GET/POST /admin/users`, `GET/PATCH /admin/users/{id}` | Create/deactivate (never hard-delete)/assign groups. |
| Groups | `group:manage` | `GET/POST /admin/groups`, `GET/PATCH /admin/groups/{id}` | Manage groups + role grants + view members. |
| Organizations | `organization:manage` | `GET/POST /organizations`, `.../{id}/members` | `POST /organizations` closes the pre-existing "no HTTP endpoint" gap from Phase 5/6. |
| Templates | `template:read`/`template:write` | `app.templates.router` (Phase 6) | Given a proper home in the Admin Portal shell this phase; same narrow read/publish surface as before. |
| Models | `provider:read` | `GET /admin/models` | Aggregates the three existing provider `.status()` checks. No install/download UI — use the `model-manager` CLI (`docs/admin/model-installation.md`). |
| Speech / Diarization | `provider:read` | same as Models | Dedicated single-provider views. |
| Processing Profiles | `processing-profile:read`/`:write` | `app.profiles.router` (Phase 6) | Extended this phase: a "New draft version" form now sets `speech_provider_config`/`diarization_provider_config` — closing the Phase 6 Known Limitation that there was no UI for these, even though the field existed. |
| Prompts | `template:read`/`:write` | `app.templates.router`'s `prompts_router` (Phase 6) | New dedicated admin page — the backend API existed since Phase 6 with no UI until now. |
| Jobs | `system:admin` | `GET /admin/jobs`, `POST /admin/jobs/{id}/retry` | Global, cross-organization view of `ProcessingJob` rows. Retry only works on a terminally FAILED job (`app.processing.service.retry_failed_job`). |
| Workers | `system:admin` | `GET /admin/workers` | Derived from `ProcessingJob.worker_id`/status/timestamps — no new worker-registry table. |
| Storage | `system:admin` | `GET /admin/storage` | Real recursive directory scan + `shutil.disk_usage`. Can be slow on a very large media volume (documented limitation, not optimized this phase). |
| Retention | `retention:read`/`:write` | `GET/POST /admin/retention-policies`, `PATCH .../{id}` | Manages the `RetentionPolicy` rows that have existed since Phase 2. **No automated enforcement/cleanup runs against them** — that's Phase 11's "Retention Cleanup" scope. |
| Authentication | `system:admin` | (static, read-only) | Shows which `AuthProviderType` is actually implemented (LOCAL only) vs. interface-only (OIDC/LDAP_AD/REVERSE_PROXY) — no new provider type added. |
| Audit | `audit:read` | `GET /admin/audit-events` | Filterable/paginated viewer over `audit_events`. Never shows conversation/fact/transcript/document content — verified by inspection of every `record_event` call site. |
| About & Licenses | `system:admin` | `GET /admin/about` | App version + a license-compliance summary + a `THIRD_PARTY_NOTICES.md` excerpt. **The production container image does not ship `compliance/`/`THIRD_PARTY_NOTICES.md`** (outside `backend/Dockerfile`'s build context) — a real deployment shows an honest "not shipped in this deployment" for the license section rather than fabricated data. |

## What "real data, not a mockup" means here

Every number/status above comes from a live query or a live provider
check at request time:
- Dashboard health calls the same `check_database_connectivity()` /
  `check_valkey_connectivity()` / provider `.status()` functions
  `app.platform.health` and the pre-existing `/admin/providers/*`
  endpoints already used.
- Queue counts are a live `SELECT count(*) ... GROUP BY status` against
  `processing_jobs`.
- Workers' "active" status requires a currently-RUNNING job with a
  non-expired lease — a worker process that isn't actually processing
  anything shows as idle, never a fabricated "connected".
- Storage figures come from actually walking the media/model directories
  and calling `shutil.disk_usage` on the real filesystem, falling back to
  the nearest existing ancestor directory if the configured root hasn't
  been created yet (fresh install).

## Known limitations

- No RAM/CPU figures beyond `os.cpu_count()` and a Linux-only
  `/proc/meminfo` read — no `psutil` dependency was added this phase
  (narrow scope, per the existing "avoid building a hardware inventory
  platform" principle). GPU/VRAM reuses Phase 3's existing
  `app.providers.device.detect_device_capabilities`.
- Storage's directory-size scan is a real, synchronous, full recursive
  walk — acceptable for an admin-triggered, infrequent call at today's
  scale, but would need optimizing (cached totals, background job) for a
  very large media volume.
- The About & Licenses page's compliance data is only available in a
  local dev checkout, not the production container image (see the table
  above) — this is a deliberate scope decision (not worth restructuring
  the Docker build context for one info page) rather than a bug.
- No new frontend unit tests were added for the ~20 new admin pages —
  verified via `tsc`/eslint/`vite build` passing, a real Docker Compose
  walkthrough (see `PHASE_7_VALIDATION_REPORT.md`), and manual code
  review, matching Phase 4/5/6's own documented precedent for new,
  narrowly-scoped admin surfaces.
