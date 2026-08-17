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

If you're implementing a later phase and considering adding something that
feels like it belongs here instead of in your phase's actual scope, add it
to this list rather than building it opportunistically.
