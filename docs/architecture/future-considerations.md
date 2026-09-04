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

## Phase 6 additions (Templates & Profiles)

- **Full template/prompt authoring UI**: `AdminTemplatesPage` (frontend)
  lists templates/versions/processing profiles and publishes a draft
  version, but creating a brand-new template/prompt or a new draft version
  from richer form fields (rather than raw JSON via the REST API) is not
  built — matching the brief's "does not need Phase 7-grade polish" scope.
  A future phase could add a real category/field editor.

- **`SpeechProfile`/`DiarizationProfile` database entities**: remains
  future work beyond Phase 7 (see
  `docs/architecture/model-management-foundation.md`) —
  `ProcessingProfileVersion.speech_provider_config`/
  `diarization_provider_config` are honestly-scoped small JSON hints, not
  a real FK to a named, multi-option provider profile table yet. Phase 7
  added the missing admin UI to *edit* these JSON hints per Processing
  Profile version (closing that specific gap), but did not promote them
  to a real named/reusable entity.

- **Per-organization Processing Profiles / Templates**: both remain
  global (platform-wide) in Phase 6, matching the existing "one global
  provider config for the whole deployment" precedent. Per-organization
  scoping (e.g. an org wanting its own custom template) is a real future
  need but not built here.

- **`ModelProfilePurpose.DOCUMENT_GENERATION`**: reserved as a data field
  on `ProcessingProfileVersion.document_model_profile_id`, but no runtime
  code path ever calls an LLM for document composition (ADR-0027 remains a
  hard constraint) — a future phase that genuinely wants an LLM-assisted
  drafting mode (as an alternative to, never a replacement for,
  deterministic composition) would need to design that as new, explicit,
  clearly-labeled functionality, not silently repurpose this field.

- **Richer PromptVersion wiring**: a published `PromptVersion`'s
  `system_prompt`/`category_instructions` only take effect when a
  `ProcessingProfileVersion` explicitly references it (Phase 6's seeded
  "general"/"meeting" profiles do not, by choice, to keep the seeded
  behavior minimal and obviously correct) — a future phase's admin UI
  should make wiring a new PromptVersion into a live ProcessingProfile a
  one-click action.

- **Contradiction detection scoped to `general_fact` only**: Meeting's new
  categories (`agenda_topic`/`decision`/`action_item`) are not checked for
  cross-fact contradictions — `app.intelligence.contradictions` remains
  scoped to `FactCategory.GENERAL_FACT` exactly as Phase 4 left it. Worth
  generalizing once a second template with genuinely comparable
  subject/attribute/value-shaped facts exists.

## Phase 7 additions (Administration / Admin Portal)

- **Dictionaries**: appears in the product spec's illustrative `/admin`
  mockup nav but is NOT in the roadmap §73 bullet list for Phase 7 —
  deliberately deferred, not built, not even a placeholder page.

- **Evaluation Lab / model comparison, Longitudinal Documentation, Service
  Accounts/API scopes/Webhooks, automated Retention Cleanup worker,
  Backup/Restore, GPU-metrics dashboard, final hardening audit**: all
  appear in the spec's illustrative full-admin-portal mockup but are
  explicitly later-phase roadmap items (Phase 8/9/10/11/12) — none were
  implemented, matching the phase brief's explicit boundary.

- **Retention Policy admin UI ships without enforcement**: Phase 7 adds
  real create/edit UI over `RetentionPolicy` rows (`/admin/retention`),
  but no scheduler/cleanup worker reads or acts on them — assigning a
  policy still only records intent. The automated enforcement job is
  Phase 11's "Retention Cleanup" scope.

- **No `SpeechProfile`/`DiarizationProfile` database entity**: Phase 7
  added an admin UI to set `speech_provider_config`/
  `diarization_provider_config` per Processing Profile *version* (closing
  the specific "no UI for these JSON hints" gap Phase 6 flagged), but
  these remain small JSON blobs on `ProcessingProfileVersion`, not a real
  named/reusable/multi-option provider-profile table. A future phase
  wanting a genuinely richer speech/diarization configuration experience
  (e.g. named presets shared across multiple Processing Profiles) would
  need that real entity.

- **Storage page's directory-size scan is a synchronous full walk**: real,
  not fabricated, but would not scale well to a very large media volume —
  a future phase could cache totals or compute them via a background job
  instead of walking the filesystem on every admin page load.

- **About & Licenses page shows no compliance data in the production
  container image**: `compliance/`/`THIRD_PARTY_NOTICES.md` are not
  COPYed into `backend/Dockerfile` (its build context is `backend/` only,
  one level below the repo root where those files live) — a deliberate
  scope decision this phase (not worth restructuring the Docker build for
  one info page), not a bug. A future phase could either widen the build
  context or embed a generated summary file inside `backend/` at build
  time.

- **No admin UI for reordering/renaming the Admin Portal navigation
  itself, no per-role customizable dashboards**: the nav structure in
  `AdminLayout.tsx` is fixed, matching the spec's mockup exactly — not
  configurable, which is intentional simplicity for this phase.

## Phase 8 additions (Analytics / Evaluation Lab / Model Lifecycle)

- **Longitudinal Documentation/Timeline, Service Accounts/API/Webhooks,
  Backup/Restore, GPU-metrics dashboard, automated Retention Cleanup,
  final hardening audit**: all remain explicitly later-phase roadmap items
  (Phase 9/10/11/12), untouched this phase.

- **No real fine-tuning/training pipeline, ever**: per spec §38, correction
  feedback and the Evaluation Lab are for quality measurement only. No
  code path in this codebase feeds conversation/correction data into a
  model-training process — this is a hard, permanent boundary, not a
  "not yet" item.

- **Evaluation Lab fixture is a single small synthetic scenario**
  (`app/analytics/fixtures.py`, `consultation_ramipril_v1`): real, honestly
  scored, but one scenario — a future phase wanting broader coverage
  (varied scenarios, more categories, longer transcripts, multiple
  languages) would add more fixtures rather than growing this one
  indefinitely. The gold-matching logic is a naive case-insensitive
  substring matcher against German-language expected values; a model that
  answers correctly but in a different language or phrasing (observed for
  real with `qwen2.5:14b`'s English-language decision text — see
  PHASE_8_VALIDATION_REPORT.md) will under-count as "unmatched" even
  though it means the same thing. A more robust (e.g. LLM-graded or
  multi-language-aware) matcher is future work, not built here to avoid
  adding a second LLM call (and its own uncertainty) into the very
  mechanism meant to measure LLM correctness.

- **Model Lifecycle checklist is an admin attestation, not automated
  verification**: `transition_model_lifecycle` requires the admin to
  assert `license_check`/`compatibility_check`/`benchmark`/
  `security_review`/`admin_approval` are all true for a forward
  transition, but nothing in this codebase actually re-runs a license
  scan or a benchmark at transition time — a future phase could wire the
  Evaluation Lab's own comparison mechanism in as an automatic "benchmark"
  checklist input (still requiring an explicit admin click to apply it),
  or link out to `compliance/check_licenses.py`'s output for the license
  check.

- **No UI/API to delete a `ModelProfileLifecycleEvent` or an
  `EvaluationRun`**: both are intentionally append-only/permanent audit
  trails (matching `FactCorrection`/`TranscriptSegmentCorrection`'s
  existing precedent) — a future phase adding data-retention rules for
  these tables should route through the existing `RetentionPolicy`
  domain rather than an ad hoc delete endpoint.

- **Technical analytics' `volume_by_day` grouping is computed in Python
  over all matching rows**, not a database-side `GROUP BY date(...)` —
  fine at today's expected admin-dataset scale (mirrors Phase 7 Storage's
  "real but not built for massive scale" disclosed limitation) but would
  not scale indefinitely; a future phase could move this to a SQL-side
  aggregation once volume warrants it.

## Phase 9 additions (Longitudinal Documentation)

- **Service Accounts/API scopes/Webhooks, Backup/Restore/GPU-metrics
  dashboard/automated Retention Cleanup, final hardening audit**: remain
  explicitly later-phase roadmap items (Phase 10/11/12), untouched here.

- **No notification/reminder/email system for Follow-ups/Tasks**: a task
  going overdue, or an AI-extracted task being created, never triggers any
  outbound notification in this codebase — Phase 10 (Integrations)
  territory per the phase brief. Today a user must open the conversation's
  Tasks tab to see open items.

- **Comparison is scoped per (organization_id, external_reference), not
  cached/precomputed**: `app.longitudinal.service.build_comparison`
  re-derives the full comparison on every request by re-reading every
  conversation's facts in the group. Fine at the expected scale of a
  single patient/case/client's conversation history (a handful to a few
  dozen conversations), but would need memoization or a persisted
  comparison-result table if a future phase needs this at much larger
  group sizes.

- **The temporal diff only compares `GENERAL_FACT` items** — `DECISION`
  and `TASK` category facts are not part of the NEW/CHANGED/NOT_MENTIONED/
  CONTRADICTED comparison (Follow-ups/Tasks already surface `TASK` facts
  through their own dedicated view). A future phase wanting "this decision
  changed between visits" comparison would need its own normalized
  key shape for `DecisionItem`/`TaskItem`, analogous to GeneralFactItem's
  (subject, attribute, value) triple — not built here since neither has an
  obvious stable identity key the way (subject, attribute) does.

- **`FollowUpTask.due_date` is a free-form string** (mirrors
  `app.intelligence.schemas.TaskItem.due_date` exactly, including
  accepting `"NOT_MENTIONED"`/unparsed natural-language phrases like "in 2
  weeks") — never parsed into a real date. No due-date sorting/reminder
  feature is possible until a future phase decides how (or whether) to
  parse these into actual dates, which the spec does not require now.

- **A task's `source_fact_id` is `ON DELETE SET NULL`, not cascaded**: if
  a `FollowUpTask`'s originating `ExtractedFact` is ever deleted, the task
  row survives (a human may already be acting on it) but silently loses
  its evidence link. No UI currently surfaces "this task's evidence was
  removed" as a distinct state — a future phase could add one if fact
  deletion becomes a real workflow (today, facts are never hard-deleted by
  any existing code path).

## Phase 10 additions (Integrations)

- **Full dual-auth (session OR API key) on every existing human-facing
  route was assessed and explicitly NOT done this phase.** Instead,
  `app.integrations.router`'s `/integrations/api/*` surface is a thin,
  additive set of routes that call the *same* domain service functions
  (`create_conversation`, `compose_document`, `approve_document`,
  `list_templates`, ...) the human routers already call — see that
  module's docstring and `PHASE_10_VALIDATION_REPORT.md`'s "Architecture
  Deviations". Retrofitting `app.identity.deps.require_permission` to
  accept a `User | ServiceAccount` union across every Phase 1-9 router
  was judged too high a regression-risk surface for one phase; a future
  hardening phase could do this properly (e.g. a shared `Principal`
  protocol) if the two-surface approach becomes a maintenance burden.

- **Webhook delivery retry is in-process (`asyncio.create_task`), not on
  the existing Valkey-backed job queue** (`app.processing.queues`). A
  process restart mid-retry loses the *pending* retry (already-made
  attempts stay durably logged in `webhook_deliveries`). Moving dispatch
  onto the real job queue for durable retries across restarts is a
  reasonable Phase 11+ hardening candidate — deliberately not built now
  to avoid adding queue-topology complexity to a phase whose merge gate
  only requires bounded retry + an accurate delivery log, not
  restart-durable retry.

- **No richer/opt-in webhook payload content option was implemented.**
  The spec allows richer payloads as an explicit admin opt-in; this phase
  ships only the safe default (ids/metadata, see
  `app.integrations.service._SAFE_PAYLOAD_KEYS`) and defers the opt-in
  richer-payload feature entirely rather than building an
  under-exercised, higher-risk content-inclusion path under this phase's
  time budget.

- **Future FHIR/HL7/PVS/KIS/CRM/Meeting-Platform adapters — architecture
  only, no implementation** (spec: prepare, do not implement
  prematurely). The extension point is exactly the Webhook mechanism this
  phase ships: a future adapter is a *webhook receiver process* (deployed
  separately, outside this repo's trust boundary) that:
  1. Is registered as an ordinary `Webhook` row, subscribed to the event
     types it cares about (e.g. `document.approved` for a FHIR
     `DocumentReference`/`Composition` export, `conversation.created` for
     a PVS/KIS appointment-linkage sync).
  2. Verifies the HMAC signature (`app.integrations.security.
     verify_signature`) exactly as any other receiver must.
  3. Uses the event's ids (never inline content, per the safe-payload
     default) to call back into the REST Integration API
     (`/integrations/api/...`) with its own `ServiceAccount` API key,
     scoped to only the resources it needs, to fetch the actual
     transcript/document/fact data it then translates into the target
     system's wire format (FHIR resources, HL7 v2 messages, a PVS/KIS/CRM
     vendor API call, a meeting-platform webhook of its own).
  4. Never runs inside the VocaDox backend process — no FHIR/HL7 parsing
     or generation library is a dependency of this repository, and no
     connector-specific UI exists in the Admin Portal beyond the
     general-purpose Service Account/Webhook management this phase adds.

  This mirrors ADR-0005's provider-abstraction pattern (define the real
  interface — here, "subscribe to events + call the scoped REST API" —
  before any concrete implementation exists) rather than speculatively
  building FHIR/HL7 code with no real deployment to validate it against.
