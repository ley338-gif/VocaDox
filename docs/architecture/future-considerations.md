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

- **Embedding/similarity-based contradiction detection**: Phase 4's
  contradiction rule (ADR-0026) only compares `general_fact` items with an
  exact-after-normalization `(subject, attribute)` match. Two facts
  referring to "the doctor" vs. "Dr. Weber", or "Blutdruckmedikament" vs.
  "Ramipril", won't be linked even if they genuinely conflict. A future
  phase could add embedding-similarity-based subject/attribute matching,
  but only once a review workflow exists that can present a
  graded-confidence signal to a human rather than a binary yes/no.

- **Full Processing Profiles system** (spec §17/§18): Phase 4 introduced
  only a minimal `ModelProfile` (id/name/provider/model_identifier/
  purpose/context_length/temperature/max_tokens/structured_output/
  version/enabled) so the extraction model isn't a hardcoded string. The
  full system — Speech Profile + Diarization Profile + Extraction Model +
  Document Model + Template + Prompt Version + Language + Retention
  Policy combined into named, admin-manageable presets like "Medical
  Consultation" — is explicitly Phase 6 scope.

- **Prompt version lifecycle management**: Phase 4's prompts
  (`app.intelligence.prompts`) are plain Python constants, not versioned
  database rows. A `prompts`/`prompt_versions` domain (spec's target
  entity list) belongs to a later phase once document generation exists
  and prompt changes need auditable history/rollback.

- **Fourth+ extraction category / domain-specific schemas** (e.g. a
  dedicated Medication schema with `dose`/`frequency`/`route` fields): the
  Phase 4 `general_fact` triple already covers the spec's own Ramipril
  example without a domain-specific schema. A fixed medical schema should
  arrive via a Template (Phase 6), not be added to the core.

- **Review Wizard UX / approval workflow**: Phase 4's `review_issues` are
  read-only (list endpoint + minimal frontend view). The full Phase 5
  workflow — "5 Punkte gefunden, 3/5 reviewed", [Richtig]/[Korrigieren]/
  [Entfernen] actions, resolution tracking, approval gating before a
  document can be finalized — is not implemented; `ReviewIssueStatus` only
  has `OPEN`/`ACKNOWLEDGED` today as a placeholder for that later work.

- **Container vulnerability scan coverage for `ollama/ollama`**: unlike
  the Phase 0-audited backend/frontend images, the `ollama` image's Trivy
  scan (this phase) found findings that could not be remediated by
  VocaDox itself (vendored Go dependencies baked into an upstream binary,
  including one CRITICAL — see `compliance/container-inventory.yml`).
  Re-scan on every Ollama version bump going forward, and track whether
  upstream ships a rebuild against patched dependencies.

- **Full pluggable Template Engine / template versions** (spec §6's target
  architecture): Phase 5's document composition uses one fixed, built-in
  template (group facts by category into three sections) — deliberately
  not the versioned, admin-editable `templates`/`template_versions` system
  the spec envisions. That belongs to Phase 6 alongside Processing
  Profiles bundling.

- **PDF/DOCX export**: Phase 5's export is deliberately plain text and
  JSON only — no new dependency was added to avoid an unresearched
  license/security decision under this phase's time budget. A future
  phase should do a real primary-source license/maintenance evaluation of
  a PDF/DOCX library (e.g. reportlab, python-docx, WeasyPrint) before
  adding either format, following the exact same primary-source-license
  discipline Phase 3/4 applied to speech/diarization/LLM dependencies.

- **Cross-conversation Timeline / longitudinal comparison** (spec's Phase
  9 scope): Phase 5's "Timeline" tab is intentionally scoped to one
  conversation's own markers/notes/processing history — comparing a
  patient/client's documents across multiple conversations over time is
  explicitly out of scope here.

- **CI coverage for `RunType.COMPOSITION`'s "no provider" precedent**: see
  ADR-0027 — composition is the first `ProcessingRun` stage with no real
  provider behind it. If a future phase adds a second such
  provider-less/synchronous stage, consider whether the
  `ProcessingJob`/worker pattern's "never inline in a request handler"
  docstring rule should be revised to state this exception explicitly
  rather than relying on each such decision re-deriving it via its own ADR.

- **Multi-fact contradiction resolution UX**: Phase 5's Review Wizard
  resolves a `POTENTIAL_CONTRADICTION` issue (which references two facts)
  by acting on exactly one targeted fact per PATCH call — a future phase
  could offer a richer "which of these two is correct" side-by-side
  comparison UI instead of the current pick-one-fact-id-explicitly flow.

If you're implementing a later phase and considering adding something that
feels like it belongs here instead of in your phase's actual scope, add it
to this list rather than building it opportunistically.
