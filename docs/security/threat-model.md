# Threat model (Phase 0 skeleton)

**Status:** initial skeleton per spec §35, §59–62. Auth itself is out of
scope for Phase 0 (spec: identity/auth land Phase 1) — this document
records the boundary now so Phase 1 implements against an agreed threat
model rather than inventing one ad hoc.

## 1. Upload handling

Media uploads (audio/video of conversations) are the primary untrusted
input surface.

- **MIME/format/size/duration validation**: uploads must be validated
  server-side against an explicit allow-list of formats before any
  processing touches them — never trust the client-supplied
  `Content-Type` header alone. Size and duration caps must be enforced
  before the file is fully buffered into memory (streaming validation),
  to prevent trivial resource-exhaustion DoS.
- **ffmpeg isolation**: any ffmpeg (or similar) invocation for
  transcoding/inspection must run as a subprocess with an argument list
  built from a fixed template — **never** shell string concatenation of
  user-controlled filenames or metadata into a command string (classic
  shell-injection vector). Use `subprocess.run([...])` with a list of
  arguments, never `shell=True` with interpolated input. This applies to
  every future domain that shells out (`media`, `transcription`,
  `diarization`).
- **No shell string concatenation from user input**, full stop — applies
  to any subprocess invocation anywhere in the codebase, not just media
  processing.

## 2. Path traversal prevention

- All persisted media/blobs use **server-generated UUID storage keys**,
  never a caller-supplied filename or path, so a malicious filename
  (`../../etc/passwd`, embedded null bytes, etc.) can never influence where
  a file is read from or written to.
- Implemented in Phase 0 by `LocalFilesystemStorage`
  (`backend/app/providers/storage.py`): `save()` always mints a fresh
  `uuid4()`-derived key; `load()`/`delete()`/`exists()` reject any key
  containing `/`, `\`, or `..`, and additionally verify the resolved path
  stays inside the storage root before touching the filesystem. Covered by
  `backend/tests/test_providers.py::test_local_filesystem_storage_rejects_path_traversal`.
- Any future `StorageProvider` implementation (e.g. object storage) must
  preserve this invariant: the caller never controls the storage key.

## 3. Secrets management

- No secret (DB password, API key, signing key) is ever hardcoded in
  source or committed to the repo. `deploy/.env.example` documents every
  required variable with placeholder/non-functional values only; the real
  `.env` is gitignored.
- `app.platform.logging.JsonFormatter` defensively redacts a fixed list of
  sensitive field names (`password`, `secret`, `token`, `api_key`,
  `authorization`, plus content fields — see §4) if they're ever
  accidentally passed to a log call, as a defense-in-depth backstop; the
  primary control is simply never logging them in the first place.
- Phase 1+ auth implementation must source signing keys / credential
  material from environment variables or a secrets manager, never from a
  config file checked into git.

## 4. Sensitive content in logs (spec §63)

Transcript text, raw audio bytes, LLM prompts/completions, and secrets must
never appear in logs. Enforced today by:
- Convention: call sites must not pass this content as log fields.
- Backstop: `JsonFormatter` redacts a fixed sensitive-key list (see
  `backend/app/platform/logging.py`).
- Test: `backend/tests/test_logging.py::test_sensitive_extra_fields_are_redacted`
  asserts the redaction actually happens.

This same rule extends to future observability additions (metrics,
tracing) — a span attribute or metric label is just as much a leak vector
as a log line.

## 5. Auth boundaries (implemented in Phase 1)

Authentication/authorization are now real, not deferred. Local
username/password auth, server-side sessions (Valkey-backed — see
[ADR-0009](../architecture/adr/0009-session-storage.md)), CSRF protection,
and genuine permission-based RBAC (`app.identity.rbac`) are implemented in
`backend/app/identity/`. What was recorded here as a Phase 1 requirement in
Phase 0 is now the actual state:

- All routers registered under `app.platform.health` remain intentionally
  unauthenticated (liveness/readiness probes must not require credentials)
  — verified: `RequestIdMiddleware`/CORS wrap them but no auth dependency
  does, and `tests/identity/test_api_auth.py` covers the auth endpoints
  without touching `/health/*`.
- `POST /api/v1/auth/login` and `POST /api/v1/auth/logout` and `GET
  /api/v1/auth/me` are the only identity endpoints; every *future* domain
  router must depend on `app.identity.deps.get_current_user` (or
  `require_permission(code)`) by default — "public by default" remains the
  wrong default and needs an explicit, reviewed opt-in per route.
- **CSRF**: a synchronizer token (`SessionData.csrf_token`), generated
  server-side at login and handed to the client once in the login response
  body (never as a separately readable cookie), must be echoed in the
  `X-CSRF-Token` header on state-changing requests
  (`app.identity.deps.require_csrf`). Verified with an integration test
  that a request carrying only the (httponly) session cookie and no/wrong
  CSRF header is rejected with 403
  (`tests/identity/test_api_auth.py::test_logout_without_csrf_header_is_rejected`,
  `::test_logout_with_wrong_csrf_token_is_rejected`).
- **Session cookie**: `httponly`, `SameSite=Lax`, and `Secure` by default
  (`VOCADOX_SESSION_COOKIE_SECURE`, disabled only in the plain-HTTP local
  dev compose stack — see `deploy/docker-compose.yml`'s comment on that
  variable). Session tokens are opaque (`secrets.token_urlsafe(32)`),
  carry no user data, and are invalidated server-side immediately on
  logout (`SessionStore.delete`) — verified end-to-end
  (`test_logout_invalidates_session`).
- **No username enumeration**: `POST /auth/login` returns an identical
  generic 401 body for "unknown username" and "wrong password" — verified
  (`test_login_rejects_inactive_user_and_does_not_leak_reason`).
- **Passwords**: Argon2id via `argon2-cffi` (see
  [ADR-0010](../architecture/adr/0010-argon2-password-hashing.md)), never
  logged, never returned by any endpoint or included in any audit event.
- **RBAC is permission-based, not role-string comparison**: every
  authorization check resolves a caller's actual permission set
  (`app.identity.rbac.get_user_permissions`, walking
  User → Group → Role → Permission) and checks for a specific code (e.g.
  `system:admin`) — there is no `if role == "admin"` anywhere in the
  codebase, and `tests/identity/test_rbac.py` exercises the resolution
  chain directly (union across multiple groups, removal of a membership
  removing the permission, etc.).
- Organization-scoped data (spec's `organizations`/`organization_memberships`)
  still needs query-layer filtering by the caller's organization
  membership once domains that own org-scoped data exist — Phase 1 only
  ships the `organizations`/`organization_memberships` foundation tables
  and basic CRUD, so this requirement carries forward unchanged to
  whichever phase adds the first org-scoped domain data.
- **Known gap, tracked, not blocking**: there is no server-side registry
  of a user's active sessions, so there is no "revoke this user's other
  sessions" admin action yet (see ADR-0009's Consequences) — acceptable
  for Phase 1 since the admin portal that would host that action doesn't
  exist until Phase 7.

## 6. Privacy-zone ("Nicht dokumentieren") handling

The product must support marking portions of a conversation as "do not
document" (privacy zones called out in the UI as "Nicht dokumentieren").
Requirements to carry into Phase 1+ implementation:

- Content inside a privacy zone must be excluded from `extracted_facts`
  generation entirely — not merely hidden in the UI after extraction. If
  extraction already ran before a zone is marked, the resulting facts must
  be deletable, not just flagged.
- Whether privacy-zone audio/transcript itself is retained at all (vs.
  redacted at the source) is a policy decision to be made explicit in a
  future ADR before Phase 1 conversation-processing ships — flagged here so
  it isn't decided implicitly by whatever the pipeline happens to do first.
- Privacy-zone boundaries themselves (timestamps) are still audit-relevant
  metadata (someone marked this zone, when) and should be captured in
  `audit_events` even though the zone's *content* is excluded from
  processing.

## Out of scope for this document

Full STRIDE-style analysis per domain, and anything specific to
authentication mechanisms (SSO, MFA, session handling) — those belong to
the `identity` domain's own design doc once Phase 1 begins.
