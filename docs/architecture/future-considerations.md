# Future considerations (scope-creep guard)

Phase 0 is scaffolding only — architecture, domain-model documentation,
provider interfaces, compliance tooling. While building it, a few concrete
Phase 1+ feature ideas came up that were deliberately **not** implemented
now, to keep Phase 0 in scope. Logged here instead of built, so they aren't
lost and aren't quietly decided by accident later.

- **Import-linter / architecture enforcement**: ADR-0001 and ADR-0002
  establish layering rules (domain packages don't depend on each other's
  internals; nothing imports the `valkey` client directly except
  `platform.valkey`) by convention only. A tool like `import-linter` could
  enforce these at CI time. Worth adding once there's enough real domain
  code for violations to actually be a risk — not needed while every
  domain package is an empty placeholder.

- **Privacy-zone retention policy**: `docs/security/threat-model.md` §6
  flags that whether privacy-zone ("Nicht dokumentieren") audio/transcript
  content is retained-but-excluded vs. redacted-at-source is an open policy
  decision. This needs its own ADR before the `conversations`/`media`
  domains implement privacy zones in Phase 1/2 — deliberately not decided
  here.

- **Structured audit event schema**: the `audit` domain's placeholder notes
  "Phase 1 (groundwork) / ongoing," but the actual `audit_events` schema
  (what fields, retention, whether it's append-only/tamper-evident) wasn't
  designed in Phase 0 beyond being listed as a target entity in
  `docs/architecture/domain-model.md`. Worth a dedicated design pass early
  in Phase 1 since audit logging is easy to bolt on badly if rushed.

- **Rate limiting / abuse protection on upload endpoints**: the threat
  model documents upload validation (MIME/size/duration, ffmpeg isolation)
  but not request-rate limiting. Reasonable to defer until the `media`
  domain's actual upload endpoint exists (Phase 2), but flagging now so
  it's designed in from the start rather than retrofitted.

- **Multi-tenancy enforcement mechanism**: `organizations` /
  `organization_memberships` are listed as target entities, but *how*
  cross-tenant isolation is enforced (row-level security in Postgres vs.
  application-layer filtering vs. both) wasn't decided — worth resolving
  before Phase 1's `identity`/`organizations` domains land real tables,
  since retrofitting RLS onto existing tables is more painful than
  designing it in.

- **Multi-tenancy enforcement mechanism, resolved for Phase 1's own
  scope**: Phase 1 shipped `organizations`/`organization_memberships` as
  foundation tables + basic CRUD only, with no row-level security and no
  application-layer org-scoped filtering yet — because no other domain's
  data exists yet to filter. The RLS-vs-application-layer decision above
  is still open and should be made before the first domain that owns
  org-scoped *data* (conversations, documents, ...) lands, not before.

- **Per-user session listing/revocation**: Phase 1's session store
  (Valkey, opaque tokens — see ADR-0009) has no secondary index from user
  → their active session tokens, so there's no way for an admin to "log
  this user out everywhere" or for a user to see/revoke their own other
  sessions. Reasonable to defer since the admin portal that would host
  that action doesn't exist until Phase 7, but worth designing the index
  in deliberately then rather than retrofitting.

- **Password strength policy beyond a length floor**: Phase 1 only
  enforces `MIN_PASSWORD_LENGTH = 12` at hash time
  (`app.identity.passwords`) — no dictionary/breach-list checks, no
  complexity rules. Worth a deliberate decision (and likely a
  `have-i-been-pwned`-style k-anonymity check, license-reviewed) before
  this becomes a real multi-user on-prem deployment, not before.

- **Account lockout / brute-force throttling on `POST /auth/login`**: Phase
  1 logs every failed attempt to `audit_events` (`login_failed`) but
  doesn't rate-limit or lock accounts after repeated failures — noted in
  the future-considerations list above under "Rate limiting / abuse
  protection," but calling it out specifically for the auth endpoint since
  it's now implemented and unprotected against credential-stuffing/brute
  force.

If you're implementing a later phase and considering adding something that
feels like it belongs here instead of in your phase's actual scope, add it
to this list rather than building it opportunistically.
