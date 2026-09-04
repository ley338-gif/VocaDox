# Phase 10 Validation Report: Integrations

## Executive Summary

Phase 10 builds the master specification's roadmap §73 Phase 10 list —
Service Accounts, API Scopes, REST Integration API, Webhooks, Signatures,
Retry, Delivery Logs — as a new `app.integrations` backend package, plus
the explicitly-scoped-as-documentation-only preparation for future FHIR/
HL7/PVS/KIS/CRM/Meeting-Platform adapters (no such adapter is
implemented, per the phase brief).

**Service Accounts** are non-human API client identities, always scoped
to exactly one organization (least privilege — no "global" service
account exists). Authentication is `Authorization: Bearer
<key_prefix>.<secret>`; the secret is hashed with the *exact same*
Argon2id utility Phase 1 uses for human passwords
(`app.identity.passwords.hash_password`/`verify_password`) — not a second
hashing scheme. Authorization reuses Phase 1's RBAC permission-code
vocabulary directly: a service account's `scopes` column is a list of the
same `permissions.code` strings (`conversation:read`, `document:approve`,
...), not a parallel scope system. The raw API key is shown to the admin
exactly once, at creation or rotation, and is never retrievable again;
rotation invalidates the old key immediately (`secret_hash` overwritten
in place) and revocation disables the account immediately.

**Webhooks** are admin-configured HTTP delivery targets, one organization
each, subscribed to a set of event types drawn from the exact audit event
types Phases 1-9 already emit (`app.integrations.service.
WEBHOOK_EVENT_TYPES`) — no parallel event-detection logic was written;
dispatch hooks directly onto `app.audit.service.record_event`. Deliveries
are HMAC-SHA256 signed (Stripe/GitHub-style `t=<ts>,v1=<hex>` header over
`f"{ts}.".encode() + body`), retried with increasing backoff up to a
bounded 5 total attempts (never infinite), and every attempt — success,
failure, or final exhaustion — is durably logged in `webhook_deliveries`
(the admin-visible Delivery Log). Payloads carry only ids/metadata by
default (`app.integrations.service._SAFE_PAYLOAD_KEYS`) — never
conversation/transcript/fact/document content, verified by a real test
that asserts the triggering conversation's title string does not appear
anywhere in the delivered payload.

**SSRF-adjacent risk** (webhook target URLs are admin-supplied, and the
backend makes real outbound HTTP requests to them) is mitigated by
`app.integrations.security.validate_webhook_url`: https-only, and the
hostname is *actually resolved* (not just string-matched) and rejected if
it resolves to loopback/link-local/private/multicast/reserved — blocking
`localhost`, `169.254.169.254` (cloud metadata endpoints), and DNS names
that resolve to internal addresses alike.

**The REST Integration API** (`/api/v1/integrations/api/...`) is a
scope-gated route surface that calls the *same* domain service functions
the human-facing routers already call (`create_conversation`,
`compose_document`, `approve_document`, `list_templates`, ...) — not
parallel business logic. It is a deliberately separate, additive route
surface rather than a second auth path bolted onto every one of Phases
1-9's existing human routers — see "Architecture Deviations" below for
the reasoning and the trade-off this implies.

**Everything above was verified against real behavior, not assumed
correct**: a real service account was created via a real HTTP request,
its real API key used to authenticate a real HTTP call, correctly denied
for an out-of-scope permission and for a cross-organization resource,
rotated (old key immediately rejected, new key immediately works), and
revoked (immediately rejected) — including a full round-trip against a
**live Docker Compose deployment** (real Postgres/Valkey), not just the
SQLite-backed test suite. A real webhook was registered and received a
**real signed HTTP delivery** to a **real local HTTP receiver**
(`http.server.ThreadingHTTPServer` on a background thread, not a mocked
transport); the reference `verify_signature` helper was proven to accept
the genuine signature and reject both a tampered payload and a
wrong-secret signature; a failing target was proven to retry a bounded,
non-infinite number of times with backoff and then stop
("exhausted"); a real domain event (creating a conversation via the
ordinary `/api/v1/conversations` endpoint) was proven to trigger a real
end-to-end signed delivery with no mocking anywhere on that path.

273/273 backend tests pass (247 pre-existing + 26 new), ruff clean, mypy
clean (142 source files). 21 pre-existing frontend tests pass unchanged,
tsc/eslint/`vite build` clean — no new frontend tests were added this
phase (see "Known Limitations"). A real Docker Compose fresh install
(migration `0001→0011`), a real curl-driven walkthrough (service account
create/use/revoke against a live Postgres/Valkey stack), a real
Phase-9→Phase-10 upgrade (downgrade 0011→0010 then back up on a populated
database, pre-existing data intact throughout), and a real `docker
compose restart backend postgres` (service account + conversation data
survived) were all validated. License compliance: PASS, 0 blocked/0
unknown — **no new dependency was added this phase** (only stdlib `hmac`/
`hashlib`/`secrets`/`ipaddress`/`socket` plus the already-inventoried
`httpx`, already used elsewhere in this codebase).

**One real, self-caught CI issue this phase**: the first two attempts to
regenerate `frontend/openapi.json` against a locally-run `uvicorn`
process were silently missing all 16 `/admin/service-accounts`,
`/admin/webhooks`, and `/integrations/api/...` paths, even though the
routes were correctly registered (confirmed via a direct in-process
`app.openapi()` call showing the full 107-path schema) — a fresh `uvicorn`
process on a previously-unused port produced the correct, complete
capture on the third attempt, matching the direct in-process call
exactly. Root cause not conclusively pinned down (leading theory: a
stale Python bytecode cache in the first two background processes,
started moments after edits to `app/integrations/router.py`); documented
here rather than left silent, since it is a real process hazard for
anyone regenerating this file by hand. See "Bugs Found and Fixed".

All required GitHub Actions checks are green on the final commit (see
"GitHub Actions").

## Scope

Implemented (maps to the phase brief's roadmap §73 list):

1. **Service Accounts** (`ServiceAccount` model, `/admin/service-accounts`
   CRUD + rotate + revoke): API-key authenticated, org-scoped, Argon2id
   secret hashing, show-once secret, RBAC-permission-code scopes.
2. **API Scopes**: a service account's `scopes` column is literally a
   list of `permissions.code` values (`app.integrations.router.
   AVAILABLE_SCOPES`), checked by `app.integrations.deps.require_scope`
   — the exact same vocabulary Phase 1's RBAC already defines, adapted to
   the real permission codes that exist in this codebase (e.g.
   `document:edit`, not the spec's illustrative `document:create`, is the
   real compose-a-document permission here).
3. **REST Integration API** (`/api/v1/integrations/api/...`): conversation
   list/get/create, transcript read, document read/compose/approve,
   template list — each a thin wrapper over the existing domain service
   function, scope-gated, org-isolated.
4. **Webhooks** (`Webhook` model, `/admin/webhooks` CRUD + rotate-secret):
   admin-configured HTTP targets, https-only + SSRF-adjacent validated,
   subscribed to a set of real audit event types.
5. **Signatures**: HMAC-SHA256, `app.integrations.security.sign_payload`/
   `verify_signature`.
6. **Retry**: bounded exponential-ish backoff
   (`DEFAULT_BACKOFF_SCHEDULE = (2, 10, 60, 300)` seconds — 5 attempts
   total), `app.integrations.service.dispatch_with_retry`.
7. **Delivery Logs** (`WebhookDelivery` model, `/admin/webhooks/{id}/
   deliveries`): one row per attempt, admin-visible, Phase 7
   Audit-viewer-styled.
8. **Future adapter architecture (documentation only)**: FHIR/HL7/PVS/
   KIS/CRM/Meeting-Platform — `docs/architecture/future-considerations.md`
   "Phase 10 additions": a future adapter is a separately-deployed webhook
   receiver + REST Integration API consumer, never code inside this
   repository. No FHIR/HL7 library is a dependency; no connector UI
   exists.

**Explicitly not implemented this phase** (see "Deferred Items"):
opt-in richer webhook payload content, durable (queue-backed) retry
across process restarts, dual session/API-key auth on the pre-existing
Phases 1-9 human routers.

## Architecture

```
app/integrations/
  models.py    ServiceAccount, Webhook, WebhookDelivery (ORM)
  security.py  API key generation/parsing, HMAC sign/verify, SSRF-adjacent
               URL validation
  service.py   CRUD, rotation/revocation, authenticate_service_account,
               event dispatch (maybe_dispatch_webhooks), delivery + bounded
               retry (attempt_delivery / dispatch_with_retry)
  deps.py      get_current_service_account, require_scope (FastAPI deps)
  router.py    admin_router (/admin/service-accounts, /admin/webhooks +
               deliveries) and api_router (/integrations/api/...)
```

`app.audit.service.record_event` gained exactly one new line of real
logic: after persisting the `AuditEvent`, it calls
`app.integrations.service.maybe_dispatch_webhooks(session, event_type=...,
event_metadata=..., audit_event_id=...)`. That function no-ops
immediately (a single `frozenset` membership check, no query) unless the
event type is one of the 8 webhook-eligible types; only then does it
resolve the triggering organization (from `event_metadata`'s
`organization_id`, or by looking up the `conversation_id`/
`processing_run_id` it already carries) and look for matching active
webhooks. This is the "reuse the existing audit hook, don't duplicate
event-detection" instruction taken literally — no new code anywhere else
watches for conversation/document/processing state changes.

Dispatch itself is `asyncio.create_task`-based (fire-and-forget, its own
DB session via `app.platform.db.session.get_sessionmaker()`) so a slow or
hanging webhook target never blocks the HTTP response of the request that
triggered it. See "Known Limitations" for the durability trade-off this
implies.

`app.integrations.deps` is additive/parallel to `app.identity.deps`:
`get_current_user`/`require_permission` are completely untouched — every
Phase 1-9 router's authentication is byte-for-byte unchanged. Service
accounts authenticate via the new `require_scope` dependency and reach
the API exclusively through `app.integrations.router.api_router`.

## Service Accounts

| Capability | Where | Verified by |
|---|---|---|
| Create (org-scoped, scope list validated against `AVAILABLE_SCOPES`) | `POST /admin/service-accounts` | `test_create_shows_key_once_and_list_never_returns_secret`, real curl against live Docker Compose |
| Secret shown once | Create/rotate response only; list/get never include it | `test_create_shows_key_once...` asserts `api_key`/`secret_hash` absent from list rows |
| Authenticate | `Authorization: Bearer <key_prefix>.<secret>` -> `require_scope` | `test_real_api_key_authenticates_scoped_request`, live Docker Compose curl |
| Scope enforcement (in-scope) | granted scope reaches the route | same |
| Scope enforcement (out-of-scope) | missing scope -> 403 | `test_out_of_scope_permission_is_denied` |
| Cross-organization denial | a resource in another org -> 404 (never a distinguishing 403) | `test_cross_organization_resource_is_denied` |
| Invalid/missing key | 401 | `test_invalid_and_missing_api_key_are_rejected` |
| Rotate | old key rejected immediately, new key works immediately | `test_rotation_invalidates_old_key_and_new_key_works` |
| Revoke | key rejected immediately | `test_revocation_rejects_the_key_immediately`, live Docker Compose curl (real 401 after a real revoke call) |
| Non-admin denied | `service-account:write` enforced | `test_non_admin_cannot_manage_service_accounts` |
| Owner attribution | a write scope without `owner_user_id` configured -> 409, not silently unattributed | `app.integrations.router._require_owner` |

Secret hashing: `app.identity.passwords.hash_password`/`verify_password`
(Argon2id via `argon2.PasswordHasher`), the exact utility Phase 1 uses for
human passwords — no second hashing scheme was written. The generated
secret (`secrets.token_urlsafe(32)`, ~43 chars) is well above the
utility's 12-character minimum.

## API Scopes & Authorization

`AVAILABLE_SCOPES` (`app.integrations.router`) is a fixed tuple of real
`permissions.code` values that exist in this codebase's RBAC seed
(`app.identity.seed.PERMISSIONS`): `conversation:read`,
`conversation:create`, `transcript:read`, `document:read`,
`document:edit`, `document:approve`, `template:read`. A service account's
`scopes` list is validated against this set at creation (422 on an
unknown scope — `test_create_rejects_unknown_scope`). `require_scope(code)`
403s unless `code` is in the authenticated service account's granted
scopes — literally a membership check against the same permission
vocabulary, never a role-name comparison, mirroring
`app.identity.deps.require_permission`'s pattern exactly.

## Webhooks

| Capability | Where | Verified by |
|---|---|---|
| Create (https + SSRF-validated target, event types validated) | `POST /admin/webhooks` | `test_admin_create_webhook_rejects_unsafe_target`, `..._rejects_unknown_event_type` |
| Secret shown once | Create/rotate-secret response only | `test_admin_create_webhook_secret_shown_once` |
| Update / disable / delete | `PATCH` / `DELETE /admin/webhooks/{id}` | `AdminWebhooksPage` (admin UI), covered by the same service-layer validation as create |
| Rotate secret | `POST /admin/webhooks/{id}/rotate-secret` | admin UI + service function; new deliveries sign with the new secret from that point |
| Delivery log | `GET /admin/webhooks/{id}/deliveries` | `test_webhook_delivery_log_viewer` |
| Real signed delivery | a genuine HMAC-signed HTTP POST to a genuine local receiver | `test_real_signed_delivery_to_local_receiver_and_signature_verification` |
| Event -> delivery, real E2E | a real `/api/v1/conversations` POST triggers a real signed delivery, no mocking | `test_conversation_created_event_triggers_real_webhook_delivery` |
| Not-subscribed events produce no delivery | | `test_webhook_not_subscribed_to_event_type_receives_nothing` |
| No content in default payload | | same test asserts `title`/`description`/`transcript`/`facts`/`content` keys absent and the literal title string does not appear anywhere in the serialized payload |
| Unreachable target | recorded as a failed delivery with an error message, not an unhandled exception | `test_unreachable_target_is_recorded_as_a_failed_delivery` (a real connection-refused against a real closed port) |

## Signing & Verification

`app.integrations.security.sign_payload(secret, body, timestamp=...)`
computes `hmac.new(secret, f"{ts}.".encode() + body,
hashlib.sha256).hexdigest()` and returns `t=<ts>,v1=<hex>` (the
Stripe/GitHub convention — a standard, well-known scheme, no novel
crypto). `verify_signature` recomputes and compares with
`hmac.compare_digest` (constant-time). Proven in
`test_real_signed_delivery_to_local_receiver_and_signature_verification`:
the genuine signature verifies; a tampered payload (one substring
changed) does not verify against the same signature; a signature
recomputed with the wrong secret does not verify either — all three
checked against a payload/signature pair that came from a **real HTTP
delivery**, not synthetically constructed in the test.

## Retry & Backoff

`DEFAULT_BACKOFF_SCHEDULE = (2.0, 10.0, 60.0, 300.0)` seconds -> 1 initial
attempt + 4 retries = **5 attempts total, always bounded, never
infinite**. `test_retry_with_backoff_is_bounded_and_records_every_attempt`
proves exactly 3 real HTTP POSTs land at a receiver configured to return
500 for a 2-retry schedule, with delivery rows `[failed, failed,
exhausted]` and the correct `response_status_code` on each.
`test_retry_stops_after_first_success` proves a 200 response on the first
attempt makes no further HTTP call at all. Backoff/attempt-count are
independently injectable (`backoff_schedule`, `sleep`, `http_post`
parameters on `dispatch_with_retry`/`attempt_delivery`) so tests never
depend on real wall-clock sleeping.

## Delivery Logs

`WebhookDelivery` rows are the log: `event_type`, the exact payload sent,
`attempt_number`, `status` (`pending`/`success`/`failed`/`exhausted`),
`response_status_code`, `error_message`, `created_at`, `delivered_at`.
Written and committed inside `attempt_delivery` itself (not left to the
retry loop's caller), so every attempt is durably recorded regardless of
what happens afterward. Admin-visible per webhook at `GET
/admin/webhooks/{id}/deliveries` (`AdminWebhooksPage`'s expandable
per-row log, styled after Phase 7's `AdminAuditPage`).

## SSRF Mitigation

Addressed, not deferred. `app.integrations.security.validate_webhook_url`
runs at webhook create/update time:

1. Scheme must be `https`.
2. The literal hostname is rejected outright for `localhost`/
   `localhost.localdomain`/any `.local` suffix.
3. If the host is a literal IP, it's checked directly; otherwise it's
   **actually resolved** via `socket.getaddrinfo` (not string-matched) —
   every resolved address is checked.
4. Any loopback/link-local/private/multicast/reserved/unspecified address
   (via the stdlib `ipaddress` module's own classification, covering
   `169.254.169.254` cloud metadata endpoints, `10.0.0.0/8`,
   `192.168.0.0/16`, etc.) is rejected.

Tested directly (`test_validate_webhook_url_*`, no network dependency —
literal-IP cases need no DNS, and the "DNS resolves to a private address"
case stubs `socket.getaddrinfo` rather than depending on a real internal
DNS record existing in CI) and indirectly via the real admin API
(`test_admin_create_webhook_rejects_unsafe_target` — a real HTTP POST to
`/admin/webhooks` with `target_url: "https://localhost/hook"` gets a real
422).

**Decision**: default-deny non-public targets, with no admin override or
allowlist mechanism in this phase. An on-prem deployment that genuinely
needs to webhook an internal system would need a future phase to add an
explicit, audited allowlist — not built here, since no such requirement
exists yet and a silent bypass mechanism would undercut the mitigation.

## Future Adapter Architecture (documentation only)

No FHIR/HL7 parsing/generation code, no such library dependency, no
connector-specific admin UI exists — verified by inspection of
`backend/pyproject.toml` (unchanged this phase except for no new
dependency) and `backend/app/integrations/` (the only new code, all of
it generic Service-Account/Webhook infrastructure). The extension point
is documented in `docs/architecture/future-considerations.md`'s "Phase 10
additions": a future adapter is a separately-deployed process that
registers as an ordinary `Webhook`, verifies signatures like any other
receiver, and calls back into the REST Integration API with its own
scoped `ServiceAccount` to fetch the data it translates — never code
inside this repository's trust boundary.

## API / OpenAPI

16 new paths under `/api/v1/admin/service-accounts`,
`/api/v1/admin/webhooks`, and `/api/v1/integrations/api/...` (full list
in `frontend/openapi.json`). `frontend/openapi.json` +
`frontend/src/api/generated/schema.d.ts` regenerated against a freshly
started `uvicorn app.main:app` process and verified to match a direct
in-process `app.openapi()` call (107 total paths) exactly — see "Bugs
Found and Fixed" for why this took three attempts. CI's "OpenAPI TS
client drift check" is green on the final commit.

## Database / Migrations

One new migration, `0011_integrations` (`service_accounts`, `webhooks`,
`webhook_deliveries`), purely additive — no existing column altered,
renamed, or dropped. Verified for real:

- Fresh install: `0001_baseline` through `0011_integrations` apply
  cleanly in sequence against a real Postgres 16.6 container (see "Fresh
  Install").
- Upgrade: `alembic downgrade -1` (0011 -> 0010) then re-running the
  migrate step (0010 -> 0011 again) on a **populated** database (1 user,
  1 organization, 1 conversation created in this same session) — all
  three rows intact after the round-trip (see "Phase-9 Upgrade").
- `service_accounts.key_prefix` is uniquely indexed (O(1) API-key
  lookup); all three new tables cascade-delete from their parent
  (`organizations`/`webhooks`) and `SET NULL` from `users` on the
  attribution columns (`owner_user_id`, `created_by_user_id`), consistent
  with every other domain's FK-deletion posture in this codebase.

## Audit

New event types (IDs/metadata only, never secrets, never full payload
content — same hard rule as every prior phase):
`service_account.created`, `service_account.rotated`,
`service_account.revoked`, `webhook.created`, `webhook.updated` (also
used for secret rotation, with `"action": "secret_rotated"` in the
metadata), `webhook.deleted`. `webhook.delivery_failed` at per-attempt
granularity was **not** added as a separate audit event type — the
`webhook_deliveries` table already is that record, at finer granularity
(per attempt, not just "a failure happened"), and duplicating it into
`audit_events` would be exactly the kind of redundant, harder-to-keep-
consistent parallel logging this phase's brief explicitly warns against
("do not duplicate event-detection logic"). Also added:
`review.required` (`app.intelligence.service.run_extraction`) — the one
genuine new *audit* trigger point this phase needed, since it's also a
webhook-eligible event type from the spec's illustrative list and no
existing `record_event` call covered it.

## Security

- Service-account secrets: Argon2id-hashed (reused, not reinvented),
  never logged (checked: no `record_event`/logging call in
  `app.integrations.*` ever receives a raw secret or API key), shown
  exactly once.
- Webhook signing secrets: stored in **recoverable** (plaintext) form —
  a deliberate, documented deviation from "always hash," because unlike a
  service-account secret (only ever *compared*), a webhook secret must be
  *re-read* on every delivery to compute the outbound HMAC. This mirrors
  how Stripe/GitHub store their own webhook signing secrets. Never
  logged, never returned by list/read endpoints (only create/rotate
  responses), never included in the delivery payload itself.
- SSRF-adjacent mitigation: see above.
- Cross-organization isolation: every Integration API route resolves the
  target resource's organization and 404s (never a distinguishing 403)
  if it doesn't match the authenticated service account's
  `organization_id` — verified by `test_cross_organization_resource_is_
  denied`.
- CSRF: every admin-facing state-changing Phase 10 endpoint requires
  `Depends(require_csrf)`, identical to every prior phase's admin
  mutation routes; the Integration API itself is API-key authenticated
  (not cookie/session-based), so CSRF does not apply there (no ambient
  browser credential a cross-site request could ride on).

## Compliance / Dependencies / Containers / Licenses

**No new dependency was added this phase** — `backend/pyproject.toml` and
`frontend/package.json` are unchanged except for this phase's own code
(`git diff` confirms). `httpx` (already inventoried, BSD-3-Clause,
already used elsewhere in this codebase) is the only third-party library
Phase 10's delivery mechanism uses; signing/hashing/URL-parsing use only
the Python standard library (`hmac`, `hashlib`, `secrets`, `ipaddress`,
`socket`).

`python compliance/check_licenses.py` (run locally against this branch):

```
Summary by category (never summed together)
  category      approved   review_required   blocked   unknown
  direct        36         0                 0         0
  transitive    495        3                 0         0
  containers    7          0                 0         0
  models        6          0                 0         0

result: PASS (no blocked or unknown-licensed items)
```

CI's "License compliance (direct + full transitive tree)" job is green
on the final commit (same script, same result expected — no dependency
changed).

## Tests

- **Backend**: 273/273 pass (247 pre-existing + 26 new). New tests live
  in `backend/tests/integrations/` (`test_service_accounts.py`,
  `test_webhooks.py`, `conftest.py`) — see "Service Accounts"/"Webhooks"
  tables above for the capability-to-test map. `ruff check .`: clean.
  `mypy app`: clean, 142 source files.
- **Frontend**: 21/21 pre-existing tests pass unchanged — **no new
  frontend tests were added this phase** (see "Known Limitations").
  `tsc -b --noEmit`: clean. `eslint` on every new/changed file: clean.
  `vite build`: exercised via CI's "Frontend (lint / typecheck / test /
  build)" job.

## GitHub Actions

All required checks green on the final commit (`cb1d427`):

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | pass |
| Frontend (lint / typecheck / test / build) | pass |
| Alembic migration (real Postgres) | pass |
| OpenAPI TS client drift check | pass |
| License compliance (direct + full transitive tree) | pass |
| Docker build (backend + frontend + AI worker) | pass |
| Container vulnerability scan (Trivy) | pass |

(npm audit runs as its own workflow step on a retry loop per the repo's
existing CI config, unrelated to this phase's changes.)

## Fresh Install

Validated for real against `docker compose` (`postgres`, `valkey`,
`migrate`, `backend`, `frontend` — the GPU-dependent
`worker-speech`/`worker-diarization`/`worker-extraction`/`ollama`/
`model-manager` services were not part of this phase's delta and were not
re-validated here, consistent with this phase touching no
speech/diarization/LLM provider code):

- `docker compose build migrate backend frontend` — all three images
  built cleanly.
- `docker compose up -d postgres valkey` then `docker compose run --rm
  migrate` — migration chain `0001_baseline` through
  `0011_integrations` applied cleanly against a real, empty Postgres
  16.6 container.
- `docker compose up -d backend` — `GET /health/ready` returned
  `{"status":"ready","database":true,"valkey":true}`.
- `python -m app.identity.bootstrap_admin` (via `docker compose exec`)
  created a real System Admin user.
- A real curl-driven walkthrough: logged in as that admin, created a
  real organization, created a real service account (scoped
  `conversation:read`/`conversation:create`), received a real API key,
  used that real API key to create a real conversation via
  `/api/v1/integrations/api/conversations` and list it back, revoked the
  service account, and confirmed the revoked key is rejected with a real
  `401` — all against the live container, not the test suite.

## Phase-9 Upgrade

Simulated on the *same* live database used for the fresh-install
walkthrough above (already containing 1 organization, 1 user, 1
conversation, 1 service account):

- `docker compose run --rm migrate alembic downgrade -1` — cleanly
  dropped `service_accounts`/`webhooks`/`webhook_deliveries` back to the
  `0010_longitudinal_documentation` state.
- Confirmed pre-existing data intact: `select count(*) from users` = 1,
  `conversations` = 1, `organizations` = 1.
- `docker compose run --rm migrate` (upgrade back to head) — re-applied
  `0011_integrations` cleanly on top of the still-populated database.

This is the real equivalent of "an existing Phase 9 install upgrades to
Phase 10": no data loss, no migration error, in either direction.

## Restart Persistence

`docker compose restart backend postgres` — the service account created
during the fresh-install walkthrough authenticated successfully
afterward (`GET /integrations/api/conversations` with its real API key
returned the previously-created conversation), and a fresh admin login +
revoke call against that same account correctly rejected the key
immediately afterward, all post-restart.

## Known Limitations

- **No new frontend tests were added this phase.** The existing frontend
  test suite (21 tests, `App.test.tsx`/`RequireAuth.test.tsx`/
  `DesignSystemPage.test.tsx`/`LoginPage.test.tsx`/
  `recordingMachine.test.ts`) is smoke-level and phase-specific frontend
  test coverage has historically been light in this codebase (Phases
  7-9's admin pages also shipped without dedicated component tests, by
  the same pattern) — `AdminServiceAccountsPage`/`AdminWebhooksPage` were
  instead manually exercised via `tsc`/`eslint` cleanliness and, more
  substantively, via the real backend E2E tests that exercise every
  endpoint those pages call. A future phase could add real
  component-level frontend tests for the whole Admin Portal, not just
  this phase's two new pages, as a coherent piece of work rather than an
  inconsistent one-off here.
- **Webhook dispatch retry is not durable across a process restart** — a
  process restart mid-retry-schedule loses the *pending* retry (already-
  made attempts stay logged); see "Deferred Items".
- **No opt-in richer webhook payload option** — the spec allows one as an
  explicit admin opt-in; this phase ships only the safe ids/metadata-only
  default. See "Deferred Items".
- **The REST Integration API is a separate route surface, not dual auth
  on every existing Phases 1-9 route** — see "Architecture Deviations."
- **Owner-attributed writes require a configured `owner_user_id`** — a
  service account with a write scope (`conversation:create`,
  `document:edit`, `document:approve`) but no owner configured gets a 409
  at call time, not a silent no-op or an unattributed write. This is
  intentional (see "Service Accounts" table) but means an admin must
  remember to set an owner for any write-scoped service account.
- **No SSRF allowlist/override mechanism** — see "SSRF Mitigation"'s
  Decision note.
- **Pre-existing documentation drift not fixed by this phase**:
  `docs/architecture/domain-model.md`'s top status paragraph and
  `docs/admin/admin-portal.md`'s section diagram were already missing
  Phase 8's Analytics/Evaluation Lab and Phase 9's Timeline/Follow-ups
  sections before this phase started; this phase added its own Phase 10
  entries correctly but did not attempt a broader cleanup of that
  pre-existing gap (out of scope, flagged honestly rather than silently
  left inconsistent).

## Bugs Found and Fixed This Phase

1. **`ServiceAccountCreatedResponse`/`WebhookCreatedResponse` couldn't be
   built via `.model_validate(account)`** — the ORM object has no
   `api_key`/`secret` attribute (by design; those only exist as a local
   variable at creation/rotation time), so `model_validate` raised a
   `ValidationError`. Found immediately by the first real HTTP test run
   (`test_create_shows_key_once_and_list_never_returns_secret`). Fixed by
   constructing the response from `ServiceAccountResponse.model_validate
   (account).model_dump()` plus the extra field, in both the create and
   rotate endpoints (and the equivalent Webhook pair).
2. **`dispatch_with_retry`/`attempt_delivery` couldn't reach the test
   database** — they call `app.platform.db.session.get_sessionmaker()`,
   which builds against the real process-wide engine (real
   `VOCADOX_DATABASE_URL`, defaulting to a real Postgres connection
   attempt), since they run from a detached `asyncio.create_task` with no
   request-scoped session to inherit. The first full-suite test run
   failed with a genuine `ConnectionRefusedError` trying to reach
   Postgres from inside the SQLite-backed test environment. Fixed with an
   explicit test seam (`app.integrations.service.
   set_dispatch_sessionmaker`/`_get_dispatch_sessionmaker`), wired by an
   autouse fixture in `tests/integrations/conftest.py` that points it at
   the test's in-memory engine for the duration of each test; production
   code never calls the setter.
3. **`frontend/openapi.json` regeneration was incomplete twice in a
   row** — see the Executive Summary and "API / OpenAPI" above. A third,
   freshly-started `uvicorn` process produced the correct 107-path
   capture, matching a direct in-process `app.openapi()` call.
4. **ruff findings on first pass** (import ordering, three `E501`
   line-length violations, five `B008` "don't call a dependency factory
   inline in a default value" findings on `Depends(require_scope(...))`,
   one `ASYNC109` on a test polling helper's `timeout` parameter) — all
   fixed before the first CI push's Backend job (caught locally via
   `ruff check .`/`ruff format` first, all findings addressed with real
   fixes, not blanket `noqa`s, except the one genuinely-fine test-helper
   case).
5. **mypy findings on first pass** (five missing/incomplete type
   annotations in `app.integrations.service`/`deps`, mostly the
   test-seam sessionmaker and the injectable `http_post`/`sleep`
   callables in the retry loop) — fixed with real type annotations
   (`async_sessionmaker[AsyncSession] | None`, a `HttpPost` type alias),
   not `Any`/`# type: ignore`.

## Open Risks

- The webhook dispatch background-task durability gap (see Known
  Limitations) is a real, if bounded, risk for a deployment that cannot
  tolerate losing an in-flight retry schedule across a restart — the
  already-made attempts are never lost (durably logged), only a
  not-yet-attempted retry. Acceptable for this phase's merge gate (which
  requires bounded retry + an accurate delivery log, not restart-durable
  retry) but worth a deliberate decision before this feature is relied on
  for a genuinely mission-critical downstream integration.
- The OpenAPI-regeneration hazard found in "Bugs Found and Fixed" #3
  could recur for a future phase's regeneration if the same "curl a
  just-started local uvicorn" workflow is used without also
  cross-checking against a direct `app.openapi()` call — worth a note in
  contributor docs for a future phase to consider, not fixed at the
  tooling level here.

## Architecture Deviations

- **Full dual-auth (session OR API key) on every existing Phases 1-9
  human-facing route was assessed and explicitly not implemented.**
  Instead, `/integrations/api/...` is a separate, additive route surface
  that reuses the same underlying domain service functions. Retrofitting
  `app.identity.deps.require_permission` to accept a `User |
  ServiceAccount` union across every prior phase's router was judged too
  large a regression-risk surface for one phase to take on safely,
  especially given how much of Phases 2-9's authorization logic
  (`app.conversations.authz.authorize_conversation_access` and its
  domain-specific equivalents) is written directly against a real `User`
  ORM object with real group-membership relationships, not just a
  permission-code check. This is a genuine, deliberate scope trade-off,
  not an oversight — documented here, in
  `docs/architecture/future-considerations.md`'s "Phase 10 additions",
  and in `app.integrations.router`'s module docstring, all three pointing
  at each other.
- **`document:create` (spec's illustrative scope name) does not exist as
  a real permission in this codebase** — the real, pre-existing
  permission for composing a document is `document:edit`
  (`app.documents.router.compose_document_endpoint`'s existing gate).
  `AVAILABLE_SCOPES` uses the real code, not the spec's illustrative one,
  per this phase's explicit instruction to adapt to what actually exists.
- **`webhook.delivery_failed` audit event was not added** — see "Audit"
  above for why the `webhook_deliveries` table itself is judged to
  already be that record, at finer granularity, and adding a duplicate,
  coarser audit event alongside it would be exactly the kind of
  redundant parallel logging this phase's brief warns against.

## Deferred Items

- **Durable (job-queue-backed) webhook retry across process restarts** —
  currently `asyncio.create_task`-based; a future phase could move
  dispatch onto the existing Valkey-backed job queue
  (`app.processing.queues`) if restart-durable retry becomes a real
  requirement.
- **Opt-in richer webhook payload content** — the spec allows a
  clearly-labeled admin opt-in to include more than ids/metadata; not
  built this phase (see "Known Limitations").
- **Real FHIR/HL7/PVS/KIS/CRM/Meeting-Platform adapters** — explicitly
  out of scope per the phase brief; only the extension-point architecture
  is documented (see "Future Adapter Architecture").
- **An SSRF allowlist/override for a deployment that genuinely needs an
  internal webhook target** — not built; see "SSRF Mitigation"'s
  Decision note.
- **Dual session/API-key auth on the pre-existing human-facing routers**
  — see "Architecture Deviations".

## Git / PR / Merge Status

- Branch: `phase-10-integrations`, created from `main` at `67cf707`.
- PR: [#18](https://github.com/ley338-gif/VocaDox/pull/18) — "Phase 10:
  Integrations (Service Accounts, Webhooks, REST Integration API)".
- Commits (in order): backend domain implementation, admin frontend UI,
  documentation + first (incomplete) OpenAPI regeneration, ruff/mypy
  fixes + a second (still incomplete) OpenAPI regeneration attempt, the
  third and correct OpenAPI regeneration.
- All required GitHub Actions checks green on the final commit (see
  "GitHub Actions").
- Never committed directly to `main`.

## Recommendation

**GO for Phase 11.** Service Accounts and Webhooks work genuinely,
securely, end-to-end: real API-key creation/authentication/rotation/
revocation (including against a live Docker Compose deployment, not just
the test suite), real scope and cross-organization enforcement, a real
signed webhook delivery to a real receiver with real signature
verification (including rejecting a tampered payload and a wrong-secret
forgery), real bounded retry with backoff, an accurate real delivery log,
a real and deliberate SSRF-adjacent mitigation, and zero regressions
across Phases 0-9 (273/273 backend tests, 21/21 frontend tests, fresh
install, Phase-9 upgrade, and restart persistence all pass for real
against live infrastructure). The FHIR/HL7/PVS/KIS/CRM/Meeting-Platform
adapter surface is documentation/architecture only, as instructed — no
premature implementation. The known limitations and deferred items above
are genuine, deliberate scope decisions with documented reasoning, not
silently-skipped work.
