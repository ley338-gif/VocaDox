# 0009 — Server-side sessions in Valkey, not a Postgres table

## Status
Accepted

## Context
Phase 1 needs authenticated sessions: server-side state keyed by an opaque
token, with expiry, and invalidation on logout. Two natural places to put
that state: a `sessions` table in Postgres, or the existing Valkey
`CacheBackend` abstraction (`backend/app/platform/valkey/backends.py`,
already used for caching — see ADR-0002).

## Decision
Sessions live in Valkey, addressed only through the existing `CacheBackend`
Protocol (`app.identity.sessions.SessionStore`) — never a new Postgres
table, and never a direct `valkey` import from the identity domain (the
same domain/platform boundary from ADR-0002, enforced by
`tests/test_architecture_boundaries.py`).

Each session is a JSON blob (`session_id`, `user_id`, `username`,
`csrf_token`, `created_at`, `expires_at`, `ip_address`, `user_agent`)
stored under `identity:session:<token>`, with Valkey's native `EX` TTL set
to `session_ttl_seconds` (`VOCADOX_SESSION_TTL_SECONDS`, default 12h) on
every `SET`. Expiry is therefore enforced two ways: Valkey drops the key
itself, and `SessionStore.get` also checks the embedded `expires_at`
defensively (so a TTL misconfiguration can't silently extend a session).
Logout calls `DELETE` on the key directly — immediate, no polling/reaping
needed.

The session token itself is `secrets.token_urlsafe(32)`: opaque and
server-generated, carrying no encoded user data, so a leaked token alone
reveals nothing about the account it belongs to (unlike a JWT, which would
carry claims in the clear even if invalid/expired if the caller mishandles
verification).

## Alternatives considered
- **Postgres `sessions` table.** Rejected for Phase 1: every request would
  need a DB round-trip (Valkey is already the faster, TTL-native primitive
  for this), and expiry cleanup would need an extra reaper job/cron that
  Valkey's native TTL gives for free. A DB table remains attractive if a
  future phase needs to *list a user's active sessions for
  admin-initiated revocation* — that's a real gap this ADR accepts for
  now (see `PHASE_1_VALIDATION_REPORT.md`, Known Limitations) and can be
  added later as a secondary index without changing where the session
  *state* itself lives.
- **Stateless JWT.** Rejected: revocation (logout, forced admin
  revocation) needs either a blocklist (which is a session store by
  another name, with extra complexity) or short-lived tokens plus refresh
  tokens (more moving parts than Phase 1's scope justifies). A stateless
  token also can't be invalidated server-side the instant `POST
  /auth/logout` is called, which the spec's security bar calls for.

## Consequences
- Valkey becoming unavailable means no one can log in or stay logged in —
  already true for caching more broadly (see `/health/ready`), so this
  doesn't introduce a new single point of failure, just raises Valkey's
  criticality.
- Session data is lost if Valkey's volume is wiped without a snapshot —
  acceptable (sessions are meant to be ephemeral; the worst case is every
  user having to log in again).
- Listing/revoking a specific user's sessions from an admin UI (a
  reasonable Phase 6/7 admin-portal feature) isn't supported by the
  current key scheme (`identity:session:<opaque token>`, no per-user
  index) and would need a small additive change, not a redesign.
