# Integrations: Service Accounts & Webhooks (Phase 10)

Two machine-to-machine primitives, managed at `/admin/service-accounts`
and `/admin/webhooks`. See `backend/app/integrations/README.md` and
`docs/architecture/domain-model.md`'s `integrations` entry for the code
map; this page is the operator-facing how-to.

## Service Accounts

A Service Account is a non-human API client, always scoped to exactly one
organization (no "global" service account exists — least privilege, and
consistent with every other org-scoped domain).

1. **Create** (`service-account:write`): pick an organization, a set of
   scopes (drawn from the same permission-code vocabulary RBAC already
   uses elsewhere — e.g. `conversation:read`, `document:approve`), and
   optionally an **owner** — an existing human user whose identity any
   write the service account makes (creating a conversation, composing or
   approving a document) is attributed to via `created_by_user_id`/
   `approved_by_user_id`, exactly as if that user had made the API call
   themselves. A write scope without an owner configured is rejected at
   call time (409), not silently attributed to nobody.
2. **The API key is shown exactly once**, immediately after creation —
   copy it now. It is never retrievable again; if lost, **Rotate** issues
   a new one (and immediately invalidates the old one).
3. **Revoke** disables the account immediately — a revoked key is
   rejected on its very next authenticated request (verified by a real
   HTTP round-trip in `tests/integrations/test_service_accounts.py`, not
   just at the DB layer).
4. **Calling the API**: `Authorization: Bearer <key_prefix>.<secret>`
   against `/api/v1/integrations/api/...` (not the human-facing
   `/api/v1/conversations/...` etc. routes — see
   `docs/architecture/future-considerations.md`'s "Phase 10 additions"
   for why this is a separate, scope-gated surface rather than a second
   auth path bolted onto every existing route).

## Webhooks

A Webhook is an admin-configured HTTP delivery target for one
organization, subscribed to a set of event types.

1. **Target URL policy (SSRF-adjacent mitigation)**: must be `https://`
   and must not resolve (the hostname is actually resolved, not just
   string-matched) to a loopback, link-local, private, multicast, or
   otherwise non-public address — this blocks a compromised/careless
   admin from pointing a webhook at an internal service or a cloud
   metadata endpoint (`169.254.169.254`). Rejected at creation/update
   time with a 422 and a specific reason.
2. **The signing secret is shown once**, at creation or after **Rotate
   secret** — update your receiver's stored secret before or immediately
   after rotating, since the old secret stops being used for *new*
   deliveries the moment you rotate.
3. **Signature verification** (what your receiver should do): the
   `X-VocaDox-Signature` header is `t=<unix_ts>,v1=<hex hmac-sha256>`,
   computed over `f"{ts}.".encode() + body`. See
   `app.integrations.security.verify_signature` for the reference
   implementation (also what `tests/integrations/test_webhooks.py`'s
   real-delivery test uses to prove a genuine signature verifies and a
   tampered payload/wrong secret does not).
4. **Payload contents**: ids and small metadata fields only — an event
   type, the event id, `occurred_at`, and whichever of
   `conversation_id`/`document_id`/`revision_id`/... apply
   (`app.integrations.service._SAFE_PAYLOAD_KEYS`). No conversation,
   transcript, fact, or document *content* is ever included by default —
   there is no opt-in richer-payload feature in this phase (see Known
   Limitations in `PHASE_10_VALIDATION_REPORT.md`).
5. **Retry**: a non-2xx response or a transport failure (timeout,
   connection refused, DNS failure, ...) retries with increasing backoff,
   bounded at 5 total attempts (1 initial + 4 retries;
   `app.integrations.service.DEFAULT_BACKOFF_SCHEDULE`), never
   indefinitely. Every attempt — success, failure, or the final
   `exhausted` state — is a row in the **Delivery Log**, visible per
   webhook in the admin UI.
6. **Disable vs. Delete**: Disable stops new deliveries but keeps the
   webhook (and its Delivery Log) for later re-enabling; Delete removes
   the row (and, via `ON DELETE CASCADE`, its delivery log) permanently.

## Event types

Exactly the audit event types already emitted by Phases 1-9 (see
`app.integrations.service.WEBHOOK_EVENT_TYPES`) — `conversation.created`,
`conversation.deleted`, `processing.started`, `processing.completed`,
`processing.failed`, `review.required` (added alongside this phase, see
`app.intelligence.service.run_extraction`), `document.created`,
`document.approved`. No new event-detection logic was written for this
phase; a webhook only ever fires from a `record_event(...)` call site
that already existed (or the one new one, above).
