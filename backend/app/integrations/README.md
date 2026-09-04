# `app/integrations/`

**Status: implemented (Phase 10, spec §54/§55, roadmap §73).**

Service Accounts (non-human API client identities, API-key authenticated,
scoped via Phase 1's RBAC permission-code vocabulary) and Webhooks
(admin-configured, HMAC-SHA256 signed, bounded-retry HTTP delivery with a
Delivery Log). See:

- `app/integrations/models.py` — `ServiceAccount`, `Webhook`,
  `WebhookDelivery` ORM models, each with a module docstring covering the
  secret-storage rationale (hashed vs. plaintext) for each.
- `app/integrations/security.py` — API key generation/parsing, HMAC
  signing/verification, SSRF-adjacent target URL validation.
- `app/integrations/service.py` — CRUD, rotation/revocation, event
  dispatch (hooked onto `app.audit.service.record_event`, not a parallel
  event-detection mechanism), delivery + bounded retry with backoff.
- `app/integrations/deps.py` — `require_scope`, the API-key-authenticated
  FastAPI dependency (additive/parallel to `app.identity.deps`, never a
  change to human-session authentication).
- `app/integrations/router.py` — `/admin/service-accounts`,
  `/admin/webhooks` (+ deliveries) admin CRUD, and the scope-gated
  `/integrations/api/...` REST Integration API surface.

See `docs/architecture/domain-model.md`'s `integrations` entry and
`docs/architecture/future-considerations.md`'s "Phase 10 additions" for
the full design rationale, the REST-Integration-API scope decision, and
the (documentation-only) FHIR/HL7/PVS/KIS/CRM/Meeting-Platform adapter
architecture. `PHASE_10_VALIDATION_REPORT.md` at the repo root has the
full validation record.
