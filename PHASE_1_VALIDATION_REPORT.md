# VocaDox — Phase 1 Validation Report

**Phase 1: Identity & Security.** Local authentication, permission-based
RBAC, Valkey-backed sessions, CSRF protection, an organizations
foundation, login audit logging, and the initial-admin bootstrap
procedure. Built on Phase 0's scaffold (merge commit `10f185c`), branch
`phase-1-identity-security`.

**Out of scope (unchanged from the roadmap):** OIDC/LDAP/reverse-proxy
implementations (interface only), conversation/media/transcription/
diarization/intelligence/review/documents/templates/profiles, the full
admin portal UI, service accounts/API scopes/webhooks, analytics.

---

## Architecture

Identity is a proper domain package (`backend/app/identity/`), following
the same interface-then-implementation pattern Phase 0 established for
`app.providers`:

- **`AuthProvider`** (`auth_providers.py`) — an ABC analogous to
  `SpeechToTextProvider`/`StorageProvider`, with `LocalAuthProvider` as
  the one real Phase 1 implementation. `AuthProviderType` (`local`,
  `oidc`, `ldap_ad`, `reverse_proxy`) is a real enum on `users.auth_provider`
  today even though only `local` has a provider class — OIDC/LDAP/reverse-
  proxy can be added later as new `AuthProvider` subclasses without
  touching `users`' shape.
- **RBAC** (`rbac.py`, `models.py`) — genuine permission-based
  authorization: `User → (user_group_memberships) → Group →
  (group_roles) → Role → (role_permissions) → Permission`.
  `get_user_permissions` is the *only* place that chain is walked; every
  authorization check (`app.identity.deps.require_permission`) resolves
  actual permission codes (`system:admin`, `conversation:create`, ...),
  never a role-name string comparison.
- **Sessions** (`sessions.py`) — deliberately *not* a Postgres table. Built
  on the existing `CacheBackend` Protocol
  (`app.platform.valkey.backends`), same domain/platform boundary Phase 0
  established for Valkey (ADR-0002) — see
  [ADR-0009](docs/architecture/adr/0009-session-storage.md) for the
  Postgres-vs-Valkey tradeoff and what it costs us (no admin
  session-listing/revocation yet, tracked in
  `docs/architecture/future-considerations.md`).
- **Password hashing** (`passwords.py`) — Argon2id via `argon2-cffi`; see
  [ADR-0010](docs/architecture/adr/0010-argon2-password-hashing.md).
- **Organizations** (`app/organizations/`) — foundation only:
  `organizations`, `organization_memberships` tables + basic CRUD
  (`service.py`). Explicitly not SaaS multi-tenancy; org-scoped filtering
  of other domains' *data* is deferred to whichever phase adds the first
  domain that owns such data (recorded in
  `docs/architecture/future-considerations.md`).
- **Audit** (`app/audit/`) — a general-purpose `audit_events` table,
  populated so far with `login`, `login_failed`, `logout`. Shaped for
  reuse by later domains; `event_metadata` carries small structured
  context only, never conversation content/passwords/tokens.
- `tests/test_architecture_boundaries.py` (Phase 0's static AST checks)
  still passes unmodified — identity code depends on `CacheBackend`
  through `app.platform.valkey`, never imports `valkey` directly, and
  never imports a concrete provider fake.

## Implementation

- **Database**: `backend/alembic/versions/0002_identity_rbac.py` — the
  first real migration. `users`, `groups`, `roles`, `permissions`,
  `user_group_memberships`, `group_roles`, `role_permissions`,
  `organizations`, `organization_memberships`, `audit_events`. Both
  `upgrade()` and `downgrade()` are hand-reviewed (not left as raw
  autogenerate output) and verified locally against real Postgres 16
  (`alembic upgrade head` → `downgrade base` → `upgrade head`, clean each
  time — see Reproducibility) and in CI (new `migration` job, Postgres
  service container).
- **REST API** (`backend/app/identity/router.py`, mounted at
  `/api/v1/auth`): `POST /login`, `POST /logout` (CSRF-protected),
  `GET /me`. Registered in `app.core.app_factory.create_app` — the first
  domain router Phase 0's factory comment anticipated.
- **Bootstrap CLI** (`backend/app/identity/bootstrap_admin.py`):
  `python -m app.identity.bootstrap_admin --username ... --display-name
  ...` — prompts for password (or accepts `--password` for scripted use),
  seeds baseline roles/permissions idempotently, creates an
  "Administrators" group with the System Admin role, refuses to run again
  once any System Admin exists unless `--force` is passed. See
  `docs/admin/README.md`.
- **RBAC seed data** (`backend/app/identity/seed.py`): the seven
  spec-defined roles (System Admin, Manager, Template Manager, Reviewer,
  User, Auditor, API Service Account) and every permission code the spec
  lists as an example, wired to the roles that should hold them.
  `apply_seed` is idempotent — safe on every bootstrap run.
- **Frontend**: `/login` page (existing design-system components —
  `Button`, `TextInput`), `AuthContext`/`useAuth` (session probe on load,
  login/logout, permission lookup), `RequireAuth`/`RequirePermission`
  route guards, `/app` (authenticated placeholder home with a working
  logout) and `/admin` (placeholder, gated on `system:admin`, proving the
  routing/permission split the spec calls for). Same-origin `/api/v1/...`
  calls — no new CORS-credential plumbing — via a Vite dev-server proxy
  (`vite.config.ts`) and an nginx proxy in the production image
  (`nginx.conf`).

## Security

- **Password hashing**: Argon2id, `MIN_PASSWORD_LENGTH = 12` enforced at
  hash time. Never logged (existing `_SENSITIVE_KEYS` redaction from
  Phase 0's structured logger still applies, and no Phase 1 code path
  passes a raw password to the logger).
- **Sessions**: opaque `secrets.token_urlsafe(32)` tokens, no user data
  encoded; httponly, `SameSite=Lax`, `Secure`-by-default cookie
  (`VOCADOX_SESSION_COOKIE_SECURE`, disabled only in the plain-HTTP local
  dev compose stack, documented inline in `deploy/docker-compose.yml`);
  server-side TTL (Valkey `EX`, default 12h) plus a defensive
  `expires_at` check in `SessionStore.get`; immediate invalidation on
  logout (`DELETE`, not a soft flag).
- **CSRF**: a synchronizer token, generated at login, handed to the client
  once in the response body (never as a separately readable cookie), must
  be echoed via `X-CSRF-Token` on state-changing requests
  (`require_csrf` dependency). Verified: a logout attempt with the
  session cookie but no/wrong CSRF header is rejected (403) — see
  `test_logout_without_csrf_header_is_rejected` /
  `test_logout_with_wrong_csrf_token_is_rejected`, and manually re-verified
  end-to-end against the live Docker stack and through the nginx
  production-image proxy path.
- **No username enumeration**: identical generic 401 body for "unknown
  username" and "wrong password" — verified
  (`test_login_rejects_inactive_user_and_does_not_leak_reason`).
- **No SQL injection surface**: all queries go through SQLAlchemy's
  parameterized query builder, same as Phase 0's existing code; no raw
  string-interpolated SQL anywhere in `app/identity`, `app/organizations`,
  or `app/audit`.
- **No secrets committed**: diff reviewed before every commit; no
  hardcoded credentials, API keys, or tokens anywhere in the branch.
- Threat model updated: `docs/security/threat-model.md` §5 rewritten from
  "deferred to Phase 1" to the actual implemented state, itemized against
  what's verified where.

## Tests

**Backend** (`backend/tests/identity/`, 46 tests, in-memory SQLite + a
fake `CacheBackend`, no external services — same convention Phase 0
established):
- `test_passwords.py` — hash/verify roundtrip, salting, min-length
  enforcement, rehash detection.
- `test_rbac.py` — permission resolution through the full chain, union
  across multiple group memberships, permission loss on membership
  removal.
- `test_auth_providers.py` — `LocalAuthProvider` success/failure paths
  (wrong password, unknown user, inactive user, non-local-provider user).
- `test_sessions.py` — create/get/delete, TTL expiry, per-session unique
  tokens/CSRF values.
- `test_bootstrap_admin.py` — first-run success, refuses a second run
  without `--force`, allows it with `--force`, refuses a duplicate
  username.
- `test_api_auth.py` — full login/logout/me integration via the existing
  httpx ASGI test-client pattern: success, wrong password, unauthenticated
  `/me`, permission resolution after login, CSRF rejection (missing/wrong
  token), session invalidation on logout, no-enumeration on failed login.

Full backend suite (`pytest -q`, including all Phase 0 tests): **72
passed** (46 new + 26 existing, all still green — architecture-boundary
checks included). `ruff check .`: clean. `mypy app`: clean (52 source
files, `disallow_untyped_defs=true`). `pip-audit`: no known
vulnerabilities.

**Frontend** (`frontend/src/`): 4 new tests
(`LoginPage.test.tsx` ×2, `RequireAuth.test.tsx` ×4) plus the 3 existing
Phase 0 tests, **9 total, all passing**. `npm run lint`: clean (0
errors). `npm run typecheck`: clean. `npm run build`: succeeds.

## CI

`.github/workflows/ci.yml` updated with one new job, `migration`: a
Postgres 16 service container running `alembic upgrade head` →
`downgrade base` → `upgrade head`, kept separate from the `backend` job
(which stays SQLite/fake-backed, no external services, per Phase 0's
existing convention) so a Postgres-specific failure is never confused
with an application-logic test failure. All other jobs (`backend`,
`frontend`, `openapi-client-drift`, `docker-build`, `compliance`,
`container-vulnerability-scan`) required no structural changes — the new
router/dependency is picked up automatically by the existing FastAPI app
factory and OpenAPI generation.

## Dependencies / Licenses

Two new direct dependencies, both researched live against the PyPI/npm
JSON APIs and both MIT:

- **`argon2-cffi`** (backend, runtime) — Argon2id password hashing. See
  ADR-0010. Transitive runtime deps `argon2-cffi-bindings` (MIT), `cffi`
  (MIT-0, already on the approved list), `pycparser` (BSD-3-Clause) — all
  already-approved licenses.
- **`@types/node`** (frontend, dev-only) — type declarations so
  `vite.config.ts`'s dev-server proxy config (`process.env`) type-checks;
  no runtime code.

`compliance/dependency-inventory-transitive.yml` regenerated using the
documented Linux-container method
(`compliance/generate_transitive_inventory.py`'s docstring — Docker
containers matching CI's `ubuntu-latest`/`python:3.11`/`node:20` images,
not run directly on this Windows host) so it matches exactly what CI will
independently regenerate and diff against.

`python compliance/check_licenses.py`: **PASS**.
- Direct: 34 approved / 0 review / 0 blocked / 0 unknown
- Transitive (426 resolved packages): 424 approved / 2 review (`certifi`,
  `pathspec`, both pre-existing Phase 0 findings, MPL-2.0, dev-tooling-only,
  documented in `compliance/exceptions.yml`, unchanged by Phase 1) / 0
  blocked / 0 unknown
- Containers: 6 approved (unchanged from Phase 0)
- Models: none

## Docker

Full stack rebuilt and verified end-to-end:
- `docker compose down -v && docker compose build --no-cache`: both
  images build clean (backend picks up `argon2-cffi`; frontend picks up
  `@types/node`).
- `docker compose up -d`: all four services (`postgres`, `valkey`,
  `backend`, `frontend`) start and reach healthy.
- `/health/live` → `{"status":"alive"}`, `/health/ready` → `{"status":
  "ready","database":true,"valkey":true}`.
- `alembic upgrade head` run inside the `backend` container: all 11
  tables created cleanly (10 domain + `alembic_version`).
- `python -m app.identity.bootstrap_admin` run inside the container:
  first admin created successfully.
- Full login → `/me` → CSRF-protected logout cycle verified against the
  live containerized backend (curl), against the Vite dev-server proxy
  (`http://127.0.0.1:5173/api/v1/...`), and against a standalone build of
  the production nginx image proxying to the real backend container over
  the compose network.
- One real bug caught and fixed during this verification: the original
  nginx `/api/` config used a literal `proxy_pass http://backend:8000/`,
  which nginx resolves once at config-load time — the image failed to
  even start (`nginx -t`: "host not found in upstream") when run outside
  the compose network (e.g. standalone container tests, or if nginx starts
  before the backend service is DNS-resolvable). Fixed by routing through
  an nginx variable + `resolver 127.0.0.11` (Docker's embedded DNS), which
  defers resolution to request time — nginx now starts regardless, and
  serves a normal 502 rather than refusing to boot if the backend isn't
  up yet. Documented inline in `frontend/nginx.conf`.

## Documentation

- [ADR-0009](docs/architecture/adr/0009-session-storage.md) — Valkey
  sessions, not a Postgres table.
- [ADR-0010](docs/architecture/adr/0010-argon2-password-hashing.md) —
  Argon2id via argon2-cffi.
- `docs/architecture/domain-model.md` — identity/organizations/audit moved
  from target-state to "implemented," with what actually shipped vs. the
  original target list (e.g. `auth_providers` is an interface, not a
  table).
- `docs/security/threat-model.md` §5 rewritten from "deferred" to
  implemented, itemized against tests/code that verify each claim.
- `docs/admin/README.md` — bootstrap-admin procedure, role/permission
  model.
- `docs/user/README.md` — signing in, session lifetime, what "Access
  denied" means.
- `docs/developer/README.md` — where identity code lives, how to add a
  new authenticated/permission-gated endpoint or a new permission/role,
  frontend auth-context file layout, how to run the identity tests.
- `docs/architecture/future-considerations.md` — four new items logged
  rather than built opportunistically: per-user session
  listing/revocation, password strength policy beyond a length floor,
  login rate limiting/account lockout, and the still-open RLS-vs-
  application-layer multi-tenancy decision (explicitly *not* resolved by
  Phase 1, since no org-scoped domain data exists yet to filter).
- `THIRD_PARTY_NOTICES.md` — updated dependency tables and counts.
- `README.md` — status banner, migration/bootstrap quickstart commands.

## Reproducibility

```bash
# Backend, from a clean checkout:
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy app
pytest -q                       # 72 passed, no external services needed

# Migration, against real Postgres (e.g. `docker compose up -d postgres valkey`):
export VOCADOX_DATABASE_URL=postgresql+asyncpg://vocadox:changeme@localhost:5432/vocadox
alembic upgrade head
alembic downgrade base          # clean drop of all 10 domain tables
alembic upgrade head            # clean re-create

# Bootstrap the first admin:
python -m app.identity.bootstrap_admin --username admin --display-name Administrator

# Frontend:
cd frontend
npm install
npm run lint && npm run typecheck && npm run test && npm run build

# Full stack:
docker compose down -v
docker compose build --no-cache
docker compose up -d
curl http://localhost:8000/health/ready
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.identity.bootstrap_admin \
  --username admin --display-name Administrator --password '<strong password>'

# License compliance:
python compliance/check_licenses.py   # PASS, 0 blocked, 0 unknown
```

## Known Limitations

- No admin UI to manage users/groups/roles beyond the bootstrap CLI —
  Phase 7's scope, not a Phase 1 regression.
- No per-user active-session listing or admin-initiated session
  revocation (ADR-0009's accepted tradeoff; tracked in
  future-considerations.md).
- No login rate limiting / account lockout on repeated failures (each
  attempt is audit-logged, but nothing throttles or blocks yet).
- Password policy is a length floor only (12 chars), no
  dictionary/breach-list checks.
- `GET /auth/me`'s on-load session probe doesn't recover a CSRF token for
  an existing (page-reload-surviving) session — a user who reloads the
  page stays logged in and can browse, but the frontend can't call
  `POST /auth/logout` for them until they next log in fresh (the backend
  session itself is unaffected; this is a frontend UX gap, documented
  inline in `AuthContext.tsx`).
- Organizations foundation only — no domain yet actually filters data by
  organization membership (nothing to filter yet).

## Open Risks

None rated Critical or unresolved-High. The two `review_required`
transitive-dependency findings (`certifi`, `pathspec`, both MPL-2.0,
dev-tooling-only) are unchanged from Phase 0 and already have recorded
sign-off in `compliance/exceptions.yml`.

## Deferred Items

See "Known Limitations" above and the four new entries in
`docs/architecture/future-considerations.md`.

## Git Status

Branch `phase-1-identity-security`, based on `main` at `10f185c` (Phase 0
merge commit). 8 commits, working tree clean, no secrets in any diff
(manually reviewed before every commit).

## Recommendation

**GO for Phase 2**, contingent on this PR's CI going green on GitHub's
hosted runners (the same bar Phase 0 was held to) and owner review. All
locally-reproducible gates pass: backend lint/typecheck/test, frontend
lint/typecheck/test/build, the Alembic migration (both directions, real
Postgres), the full Docker stack (build, health, migration, bootstrap,
login/logout/me through every network path including the production nginx
proxy), and the license compliance gate (0 blocked, 0 unknown). No
Critical/unresolved-High security findings. Per the standing process, do
not begin Phase 2 (Conversation Capture) work until the owner gives
explicit GO, matching Phase 1's own start.
