# Phase 6 Validation Report: Templates & Profiles

## Executive Summary

Phase 6 makes VocaDox's extraction/composition pipeline genuinely
template-driven instead of hardcoded. It adds a real Template Engine
(`Template`/`TemplateVersion`, spec §42) where publishing never mutates a
version in place; a Prompt lifecycle (`Prompt`/`PromptVersion`, spec §43:
DRAFT → TEST → PUBLISHED → RETIRED); a Model Profile that graduates from
Phase 4's minimal foundation into a real, versioned, admin-manageable
entity (spec §18); the new Processing Profile system bundling
template + extraction model + language + retention into named, friendly
presets (spec §19); and the Configuration Hierarchy resolver
(`SYSTEM DEFAULT → PROCESSING PROFILE → CONVERSATION OVERRIDE`, spec §20)
with genuine per-field explainability.

The "General Conversation" template reuses Phase 4/5's exact builtin
extraction schemas byte-for-byte (verified by a direct Pydantic-class
identity assertion), so nothing about existing conversations' extraction/
composition behavior changed. "Meeting" is a real, independently-defined
template (agenda_topic / decision-with-rationale / action_item-with-owner)
proving the engine drives genuinely different behavior, not a relabeled
copy — verified end-to-end against both a fast in-process test and a real
Docker Compose deployment, where General and Meeting conversations
produced different fact categories, different document section titles,
and different `template_version_id` values on their composed revisions.

Three real, pre-existing, unrelated issues were found and fixed during
this phase, all matching the exact "rolling dependency drift" pattern
Phase 4 (FFmpeg) and Phase 5 (ruff) each documented: an upstream fastapi/
starlette version gap broke several `204 No Content` routes and a status-
code constant name; the committed `frontend/openapi.json` had drifted
from what a truly fresh dependency install produces; and the license-
compliance transitive inventory needed regeneration for the same
fastapi/starlette/pydantic bump (twice — the second regeneration fixed an
error in the first, where the `[ai]` extra's GPU/CUDA13 torch wheel was
scanned instead of the CPU-only wheel `backend/worker.Dockerfile` actually
ships, which briefly and incorrectly showed 1 blocked + 16 unknown NVIDIA
proprietary packages). A fourth, currently-live external issue (npm's
classic "quick audit" endpoint intermittently hanging/erroring, per npm's
own retirement notice) was mitigated with a bounded retry in the CI
workflow rather than ignored.

Every automated check is green on the final commit, both workflow runs:
184 backend tests (173 pre-existing + 11 new), ruff/mypy clean; 21
pre-existing frontend tests unchanged, tsc/eslint/vite build clean, no
OpenAPI drift. Migration `0008` was validated against a real Postgres:
full `0001→0008` chain, a `downgrade -1`/`upgrade head` cycle, a full
`downgrade base`/`upgrade head` cycle, and a genuine Phase-5-data upgrade
rehearsal (pre-existing org/conversation/model_profile/document/
document_revision rows survive unchanged with every new column correctly
defaulted to NULL). Fresh install, the General-vs-Meeting end-to-end
proof, and restart persistence were all validated against a real `docker
compose` stack (not just the fast in-process test suite). License
compliance: PASS, 0 blocked/0 unknown across all four categories.

## Scope

Implemented (maps to the phase brief's Phase 6 scope):

1. **Template Engine** (`app.templates`): `Template`/`TemplateVersion`,
   never mutated once published — publishing retires the prior version
   (frozen by an ORM `before_update` guard) and re-points the template at
   the new one. `app.templates.schema_builder` turns a version's JSON
   `extraction_categories` into real Pydantic schemas: `builtin: true`
   entries resolve to Phase 4/5's exact, unchanged classes; anything else
   is built dynamically via `pydantic.create_model`. See ADR-0028.
2. **Seeded templates**: `general` (published, the 3 exact builtin
   categories), `meeting` (published, genuinely different: agenda_topic/
   decision-with-rationale/action_item-with-owner), `medical_consultation`
   and `psychotherapy` (DRAFT-only foundation, never published, per the
   brief's "prepared as foundation only").
3. **Prompt lifecycle** (`app.templates.models.Prompt`/`PromptVersion`,
   spec §43): DRAFT → TEST → PUBLISHED → RETIRED. A published
   `PromptVersion`'s `system_prompt`/`category_instructions` genuinely
   change extraction wording when a `ProcessingProfileVersion` references
   it (`app.processing.orchestrator.execute_extract`), not just recorded
   for provenance.
4. **Model Profiles** (spec §18): `ModelProfile` extended with
   `thinking_mode`/`configuration` columns; `ModelProfileVersion` snapshots
   the pre-edit state on every `PATCH /api/v1/model-profiles/{id}`.
5. **Processing Profiles** (spec §19): `ProcessingProfile`/
   `ProcessingProfileVersion` bundling Speech/Diarization provider config
   (Settings-driven hints — a real `SpeechProfile`/`DiarizationProfile` DB
   entity remains Phase 7) + Extraction Model + (reserved) Document Model +
   Template + Template Version + Prompt + Prompt Version + Language +
   Retention Policy. `GET /api/v1/processing-profiles` returns only the
   friendly fields (readable by the standard `User` role); technical
   composition is admin-only. Seeded: `general` (`is_system_default=true`)
   and `meeting`, both published.
6. **Configuration Hierarchy** (spec §20): `app.profiles.resolver
   .resolve_effective_config` implements SYSTEM DEFAULT → PROCESSING
   PROFILE → CONVERSATION OVERRIDE with per-field `field_sources`
   explainability. `GET /conversations/{id}/effective-config` and
   `PATCH /conversations/{id}/config-override` expose it.
7. **Wiring into extraction/composition**: `execute_extract` resolves the
   effective template/model/prompt and records all three ids on the
   `ProcessingRun` (spec §43's reproducibility requirement, with a
   documented fallback to Phase 4's `get_active_profile()`-only behavior
   if no system-default profile is seeded yet). `compose_document` resolves
   the effective template for section presentation and records
   `template_version_id` on the `DocumentRevision`. `run_extraction`'s new
   parameters all default to `None`/general, so every pre-Phase-6 caller
   (including Phase 4's own tests) is unaffected.
8. **New RBAC permissions**: `template:read`/`template:write`,
   `model-profile:read`/`model-profile:write`,
   `processing-profile:read`/`processing-profile:write` — granted to
   System Admin (all) and Template Manager (all six); `template:read`/
   `processing-profile:read` also granted to the standard `User` role so
   end users can see template info and pick a friendly profile name. The
   pre-existing `profile:write` code (seeded since Phase 1 in anticipation
   of this phase) is kept as a documented deprecated alias.
9. **Admin-facing REST surface**: `app.templates.router`
   (Templates/Prompts CRUD + versioning + publish) and `app.profiles
   .router` (Model Profiles CRUD/versioning, Processing Profiles
   CRUD/versioning/publish) — global/platform-wide, not organization-
   scoped, matching the existing "one global provider config" precedent.
10. **Frontend**: `/admin/templates` (gated `template:read`) lists
    templates/versions/categories with a publish action, plus read-only
    Processing/Model Profile views — narrowly scoped per the brief, not
    Phase 7-grade. `NewConversationPage` gains a Processing Profile
    selector sourced from `GET /processing-profiles`.
11. **Conversation model**: `processing_profile_id` (the PROCESSING
    PROFILE layer) and `config_overrides` (the CONVERSATION OVERRIDE
    layer), both additive/nullable.
12. **Database**: migration `0008_templates_profiles` — `templates`,
    `template_versions`, `prompts`, `prompt_versions`,
    `model_profile_versions`, `processing_profiles`,
    `processing_profile_versions`, plus additive columns on
    `model_profiles`/`conversations`/`processing_runs`/
    `document_revisions`. No existing column dropped or renamed.
13. **Tests**: 11 new (`tests/templates/`, `tests/profiles/`) — template
    versioning/immutability/RBAC, prompt lifecycle, model profile
    versioning, and the merge-gate proof (General vs Meeting genuinely
    different end-to-end, config hierarchy explainability).
14. **Documentation**: `docs/architecture/templates.md` (new),
    ADR-0028, updates to `intelligence-pipeline.md`/`documents.md`/
    `model-management-foundation.md`, `future-considerations.md`'s Phase 6
    additions, and the missing ADR-0027 index entry (a Phase 5 omission).

**Explicitly out of scope, not implemented** (per the brief): the rest of
the Phase 7 Admin Portal, Analytics/Evaluation Lab, cross-conversation
Longitudinal Documentation, Service Accounts/Webhooks, Worker/GPU
dashboards, a `SpeechProfile`/`DiarizationProfile` database entity. See
`docs/architecture/future-considerations.md`'s Phase 6 additions for the
itemized list.

## Architecture

See `docs/architecture/templates.md` for the full design and
`docs/architecture/adr/0028-dynamic-template-extraction-schemas.md` for
why extraction categories build Pydantic schemas dynamically rather than
requiring a hand-written class per category.

## Template Engine

`Template` (stable identity, `key`) / `TemplateVersion` (immutable-once-
published content: `extraction_categories`, `presentation`, reserved
`review_rules`). Publishing (`app.templates.service
.publish_template_version`) retires the previous published version
(status flips to `RETIRED`, content frozen by an ORM `before_update`
guard identical in spirit to `app.documents.models`'s revision-
immutability guard) and re-points `Template.current_published_version_id`
— proven by `test_create_version_publish_never_mutates_prior_version`,
which publishes v1, publishes a genuinely different v2, and asserts v1's
`extraction_categories` are byte-identical to what was originally
published and its status is `retired`, never deleted.

Seeded templates: `general` (published) exactly reproduces the 3 Phase
4/5 builtin categories (`general_fact`/`decision`/`task`, each marked
`builtin: true`); `meeting` (published) is genuinely different
(`agenda_topic`/`decision`-with-rationale/`action_item`-with-owner/due/
priority); `medical_consultation`/`psychotherapy` are seeded but
deliberately left unpublished (draft-only foundation).

## Model Profiles

`ModelProfile` gained `thinking_mode`/`configuration` (additive/nullable)
and a real version history: `app.profiles.service.update_model_profile`
snapshots the pre-edit state into a new `ModelProfileVersion` row before
applying any change — proven by
`test_update_model_profile_snapshots_prior_state_as_a_version`, which
edits `temperature` and confirms the v1 snapshot still shows the
*original* value, not the edited one.

## Processing Profiles

`ProcessingProfile` (`key`, friendly `name`, `is_system_default`) /
`ProcessingProfileVersion` (the technical bundle: speech/diarization
config, extraction model, template + version, prompt + version, language,
retention policy). Seeded: `general` (`is_system_default=true`) and
`meeting`, both referencing the seeded extraction `ModelProfile` and their
respective template's published version. `GET /api/v1/processing-profiles`
(granted to the standard `User` role) returns only friendly fields.

## Configuration Hierarchy

`app.profiles.resolver.resolve_effective_config(session, conversation)`:

1. **SYSTEM DEFAULT** — the one `ProcessingProfile` with
   `is_system_default=true` (seeded as `general`).
2. **PROCESSING PROFILE** — if `conversation.processing_profile_id` names
   a profile with a published version, every field is overridden from it.
3. **CONVERSATION OVERRIDE** — `conversation.config_overrides` (JSON,
   keyed by the same field names) overrides individual fields on top of
   whichever of the first two layers won.

`EffectiveConfig.field_sources`/`.explain()` records which layer set each
winning value. Verified against a real Docker deployment: a conversation
with no profile chosen showed every field sourced `system_default`; the
same conversation after `PATCH .../config-override` showed the overridden
field sourced `conversation_override` while untouched fields stayed
`system_default`; a Meeting conversation showed every field sourced
`processing_profile`. Also covered by
`test_effective_config_shows_processing_profile_layer_for_meeting_conversation`.

## Backward Compatibility with Phase 4/5

- `run_extraction`'s `template_version`/`system_prompt`/
  `category_instruction_overrides` parameters default to `None`/general,
  resolving to the exact pre-Phase-6 behavior for every existing caller
  (verified: `tests/intelligence/test_pipeline_extraction.py`'s calls,
  unmodified, still pass).
- The "general" template's `builtin: true` categories reference
  `EXTRACTION_CATEGORIES`'s exact Pydantic class objects — verified by a
  direct identity assertion (`resolve_category(...).schema_cls is
  GeneralFactsExtraction`) during manual validation, and indirectly by
  `tests/intelligence/test_schemas.py` (imports those classes directly)
  passing unmodified.
- `compose_document`'s rendering for `general_fact`/`decision`/`task`
  facts whose `structured_value` keys match exactly what those categories
  always produced is unchanged (`_render_statement`'s builtin-shape
  branches); a genuinely different category (e.g. Meeting's `action_item`)
  falls through to a new generic "field: value" renderer.
- Every new column is additive/nullable — see Database section.
- **173 pre-existing backend tests pass unmodified**; 21 pre-existing
  frontend tests pass unmodified.

## API / OpenAPI

New endpoints: `GET/POST /templates`, `GET/POST /templates/{id}/versions`,
`POST /templates/{id}/versions/{vid}/publish`, `GET/POST /prompts`,
`GET/POST /prompts/{id}/versions`,
`POST /prompts/{id}/versions/{vid}/publish`, `GET/POST /model-profiles`,
`PATCH /model-profiles/{id}`, `GET /model-profiles/{id}/versions`,
`GET/POST /processing-profiles`, `GET/POST
/processing-profiles/{id}/versions`, `POST
/processing-profiles/{id}/versions/{vid}/publish`,
`GET /conversations/{id}/effective-config`, `PATCH
/conversations/{id}/config-override`. `frontend/openapi.json` and
`schema.d.ts` regenerated against a live backend instance (matching the
exact method CI's drift-check job uses: curl a running uvicorn's
`/openapi.json`, no manual reformatting) — CI's "OpenAPI TS client drift
check" job: **PASS** on both final workflow runs.

## Database / Migrations

`backend/alembic/versions/0008_templates_profiles.py` adds `templates`,
`template_versions`, `prompts`, `prompt_versions`,
`model_profile_versions`, `processing_profiles`,
`processing_profile_versions`; extends `model_profiles`
(`thinking_mode`/`configuration`), `conversations`
(`processing_profile_id`/`config_overrides`), `processing_runs`
(`template_version_id`/`prompt_version_id`/`processing_profile_version_id`),
`document_revisions` (`template_version_id`) — every extension additive
and nullable. Circular FK pairs (`templates.current_published_version_id`
↔ `template_versions.template_id`, same pattern for
`prompts`/`processing_profiles`) resolved the same way Phase 5 resolved
`documents`/`document_revisions`: parent created first without the FK,
child created with its FK to the parent, then the parent's FK added via
`ALTER TABLE`.

Verified against a real Postgres 16 container:
- Full chain `0001→0008` applied cleanly.
- `alembic downgrade -1` / `alembic upgrade head` cycled cleanly.
- Full `alembic downgrade base` / `alembic upgrade head` cycled cleanly.
- **A genuine Phase-5-data upgrade rehearsal**: downgraded to `0007`,
  inserted real organization/conversation/model_profile/document/
  document_revision rows via raw SQL matching Phase 5's exact schema, ran
  `alembic upgrade head`, and confirmed via direct `SELECT` that the
  document revision's `rendered_text` was untouched with
  `template_version_id` correctly defaulted to `NULL`, and the model
  profile's pre-existing row gained `thinking_mode`/`configuration` as
  `NULL` — a real migration-safety proof, not merely asserted.
- CI's "Alembic migration (real Postgres)" job: **PASS** on both final
  workflow runs.

## Authorization

New endpoints gated by the new permission codes
(`template:read`/`write`, `model-profile:read`/`write`,
`processing-profile:read`/`write`) via `app.identity.deps
.require_permission` — global/platform-wide (no organization scoping, by
design, matching the "one global provider config" precedent already
established for provider status endpoints). `test_template_write_requires
_permission`/`test_model_profile_write_requires_permission` verify a
standard `User` (has `template:read`/`processing-profile:read` but not
the `:write` codes) gets 403 on write attempts. Conversation-scoped
endpoints (`effective-config`, `config-override`) go through the existing
`authorize_conversation_access` with `conversation:read`/`conversation
:update` respectively — identical cross-organization enforcement to every
prior phase.

## Audit

`template.published`, `prompt.published`, `model_profile.created`,
`model_profile.updated`, `processing_profile.published`,
`conversation.config_override_updated` — all carry only ids/version
numbers/field-name lists, never template/prompt content.

## Security

No code path in the new Phase 6 modules ever calls an LLM for document
composition — `ModelProfilePurpose.DOCUMENT_GENERATION` is a reserved
data field only (`ProcessingProfileVersion.document_model_profile_id`),
never read by any runtime code path; verified by inspection of
`app.documents.service` (unchanged LLM-free composition, ADR-0027 remains
intact) and by grep across the new `app.templates`/`app.profiles` modules
for any `app.providers.llm` import outside `app.intelligence.service`
(the one, pre-existing, extraction-only call site).

## Compliance / Dependencies / Models / Containers / Licenses

**No new direct dependency was added this phase** (`backend/pyproject.toml`
and `frontend/package.json` are byte-identical to their pre-Phase-6
state). The transitive inventory still needed two regenerations, both
purely due to an upstream fastapi/starlette/pydantic version bump that
happened to be picked up incidentally while investigating the OpenAPI
drift check (a fresh `pip install -e ".[dev]"` today resolves
fastapi 0.141.1/starlette 1.6.0/pydantic 2.13.5 vs. an earlier, already-
stale local environment's fastapi 0.116.1/starlette 0.47.3/pydantic
2.13.4 — the constraint range itself, `fastapi>=0.115,<1.0`, was never
touched):

| Category | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies | 36 | 0 | 0 | 0 |
| Transitive (498 resolved packages) | 495 | 3 | 0 | 0 |
| Container images | 7 | 0 | 0 | 0 |
| AI models | 6 | 0 | 0 | 0 |

`compliance/check_licenses.py` → **PASS**. CI's "License compliance"
job: **PASS** on both final workflow runs.

**A real, self-caught near-miss during this phase's own regeneration**:
the first attempt to regenerate `compliance/dependency-inventory-
transitive.yml` omitted the `[ai]` extra's scan entirely, silently
dropping ~74 worker-scope packages; a corrected second attempt that
scanned `pip install -e "backend/[ai]"` *without* the
`--extra-index-url https://download.pytorch.org/whl/cpu` flag
`backend/worker.Dockerfile` actually uses picked up a default GPU/CUDA13
torch wheel and surfaced 1 blocked + 16 unknown NVIDIA proprietary
packages — packages the real shipped worker image never installs at all.
The final, correct regeneration used the exact command CI's own
"License compliance" workflow step uses (verified by reading
`.github/workflows/ci.yml` directly), landing back at the 498-package/
0-blocked/0-unknown baseline. Documented here in full because it's exactly
the kind of "looked blocked, wasn't" investigation the compliance process
exists to catch and resolve correctly rather than either panicking or
rubber-stamping.

`pip-audit`: no known vulnerabilities.

## Tests

**Backend**: 184 passed (173 pre-existing + 11 new), ruff clean, mypy
clean (120 source files).

New test breakdown:
- `tests/templates/test_versioning.py` (4): seeded general/meeting
  templates exist and are (or aren't, for the draft-only ones) published;
  Meeting's categories are genuinely different from General's (different
  category keys, non-builtin, distinct field lists); publish never
  mutates the prior version's content; `template:write` RBAC enforcement.
- `tests/templates/test_prompts.py` (2): seeded prompts exist and
  general's is published; full DRAFT→PUBLISH→new-DRAFT→PUBLISH lifecycle
  with the retired version's content unchanged.
- `tests/profiles/test_model_profiles.py` (3): seeded extraction
  ModelProfile exists via the API; `PATCH` snapshots the pre-edit state as
  a new version; `model-profile:write` RBAC enforcement.
- `tests/profiles/test_meeting_vs_general_e2e.py` (2): the merge-gate
  proof — full API-driven pipeline (create conversation with/without a
  Processing Profile → transcribe → extract via a category-aware stub LLM
  provider → compose) shows General and Meeting produce different fact
  categories, different document section titles, and different
  `template_version_id` values; the effective-config/config-override
  explainability round trip.

**Frontend**: 21 pre-existing tests pass unchanged; tsc/eslint/`vite
build` all clean. No new frontend unit tests were added for
`AdminTemplatesPage.tsx`/the new `api/profiles.ts`/`api/templates.ts` —
verified via `tsc`/eslint/`vite build` passing and manual code review,
matching Phase 4/5's own documented precedent for equally new, equally
minimal frontend surfaces.

## GitHub Actions

All 7 required checks green on the final commit (`ecd5248`, merged as
`5ecefc9`), both workflow runs:

| Check | Result |
|---|---|
| Backend (lint / typecheck / test) | PASS |
| Frontend (lint / typecheck / test / build) | PASS |
| Alembic migration (real Postgres) | PASS |
| OpenAPI TS client drift check | PASS |
| License compliance (direct + full transitive tree) | PASS |
| Docker build (backend + frontend + AI worker) | PASS |
| Container vulnerability scan (Trivy) | PASS |

**Real CI issues found and fixed during this phase** (beyond the
compliance regenerations above):
1. Several `204 No Content` routes (`DELETE /conversations/{id}`, media/
   participant/marker/note deletes, `POST /auth/logout`) needed an
   explicit `response_model=None` — a newer fastapi's stricter assertion
   treats a bare `-> None` return annotation as a truthy `NoneType`
   response model rather than "no response model", which is incompatible
   with a 204 status. Root-caused via a side-by-side `git stash` test
   proving the failure was pre-existing on `main`, not introduced by this
   phase.
2. `HTTP_422_UNPROCESSABLE_CONTENT` — never a valid constant in the
   starlette version an earlier, stale local environment had installed;
   momentarily "fixed" to `HTTP_422_UNPROCESSABLE_ENTITY`, then correctly
   reverted once a fresh install confirmed starlette 1.6.0 restores
   `HTTP_422_UNPROCESSABLE_CONTENT` as the actual non-deprecated name
   (`HTTP_422_UNPROCESSABLE_ENTITY` now emits a deprecation warning).
3. npm's classic "quick audit" endpoint intermittently hangs for minutes
   then fails with inconsistent transient errors (503, then a 400
   "Invalid package tree" that never reproduces locally) — npm's own CLI
   now prints a retirement notice for this exact endpoint. Mitigated with
   a bounded 3-attempt/120s-timeout retry in `.github/workflows/ci.yml`
   rather than ignored or worked around by disabling the check.

## Fresh Install

Validated for real against `docker compose` (excluding `ollama`/
`model-manager`, matching Phase 4/5's own fresh-install validation scope —
extraction/speech/diarization default to `fake` providers per
`deploy/docker-compose.yml`'s `VOCADOX_*_PROVIDER:-fake` defaults):

- `docker compose down -v` (clean slate) → `docker compose build migrate
  backend worker-speech worker-diarization worker-extraction frontend` →
  all images built successfully.
- `docker compose up -d postgres valkey migrate backend worker-speech
  worker-diarization worker-extraction frontend` — `migrate` ran the full
  `0001→0008` chain against a fresh Postgres 16 container; all seven
  services reached a running/healthy state; no errors in any worker log.
- `python -m app.identity.bootstrap_admin` created the first System Admin
  user and applied the RBAC/model-profile/template/processing-profile
  seeds (idempotent, real DB commit).
- Real HTTP walkthrough end-to-end: login → create organization +
  membership (via a one-off script, same pre-existing Phase 1/2 gap
  Phase 5 documented — organization creation has no HTTP endpoint yet) →
  `GET /processing-profiles` returned the real seeded General/Meeting
  profiles → created two conversations, one with no profile (SYSTEM
  DEFAULT layer) and one with `processing_profile_id` set to Meeting →
  `GET .../effective-config` on each showed the correct layer sourcing
  (`system_default` vs `processing_profile`) → uploaded synthetic WAV to
  both → `POST .../process/transcript` (fake provider) → both reached
  `ready` → `POST .../process/extract` (fake provider) → both reached
  `ready` again → `POST .../document/compose` on both → **200 with
  genuinely different `template_version_id` values** → `POST
  .../document/approve` on the general one → `200 approved` → `GET
  .../document/export?format=text` → `200` with real content.

## Phase-5 Upgrade Validation

Covered under Database/Migrations above: a genuine Phase-5-schema-with-
real-data rehearsal (downgrade to `0007`, insert real rows matching Phase
5's exact schema, upgrade to `0008`, confirm via direct SQL that
pre-existing data survived unchanged with new columns correctly
defaulted). A true from-a-tagged-Phase-5-checkout rehearsal (checking out
the Phase 5 merge commit and running its full stack, then switching
branches) was not performed end-to-end in this session, matching the
exact limitation Phase 4/5 each disclosed for their own prior-phase
upgrade validation — the same-schema-with-real-data rehearsal plus the
full fresh-install chain validated above is strong evidence the upgrade
path is safe, consistent with that precedent's reasoning (migration 0008
only adds tables/columns, no `ALTER`/`DROP` of existing data).

## Restart Persistence

`docker compose restart backend postgres` — the composed document
(status `ready_for_approval`, revision content, `template_version_id`)
created before the restart was confirmed byte-identical via a real `GET
/conversations/{id}/document` call afterward, not assumed from `docker
volume ls`.

## Known Limitations

- **No frontend unit tests for the new admin surface**
  (`AdminTemplatesPage.tsx`, `api/profiles.ts`, `api/templates.ts`) —
  verified via `tsc`/eslint/`vite build` passing and manual code review,
  matching Phase 4/5's identical, explicitly disclosed gap for their own
  new frontend surfaces.
- **PromptVersion wiring is opt-in, not automatic**: the seeded
  `general`/`meeting` `ProcessingProfileVersion`s don't reference a
  `PromptVersion` (they use the template's own category instructions
  directly) — a published `PromptVersion` only changes extraction wording
  once an admin explicitly wires it into a `ProcessingProfileVersion`.
  Functionally complete and tested independently (prompt lifecycle,
  and the orchestrator code path that consumes it when present), just not
  demonstrated together in the seed data. Logged in
  `future-considerations.md`.
- **Speech/Diarization remain Settings-driven, not a real
  `SpeechProfile`/`DiarizationProfile` DB entity** — an explicit,
  documented Phase 7 scope boundary (`model-management-foundation.md`),
  not an oversight.
- **Templates/Processing Profiles are global, not per-organization** — by
  design, matching the existing "one global provider config" precedent;
  a real future need, not built here.
- **Contradiction detection remains scoped to `general_fact`** — Meeting's
  new categories are not cross-checked for contradictions, unchanged from
  Phase 4's original scoping decision.
- **No true from-a-tagged-Phase-5-checkout upgrade rehearsal** — see
  Phase-5 Upgrade Validation above for what was actually done instead and
  why it's still strong evidence, matching Phase 4/5's own documented
  precedent for this exact gap.
- **Organization creation has no HTTP endpoint** — a pre-existing Phase
  1/2 gap, encountered but not introduced by this phase's fresh-install
  validation (same as Phase 5's disclosure).

## Open Risks

None new this phase. The Ollama container's accepted CRITICAL finding
from Phase 4 (`compliance/container-inventory.yml`'s `ollama/ollama`
entry) remains open and tracked exactly as Phase 4/5 left it — this phase
did not touch the LLM provider or its container.

## Architecture Deviations

None from the phase brief's explicit scope. The one deliberate deviation
from a *prior* phase (synchronous document composition, ADR-0027) is
unchanged and untouched by this phase.

## Deferred Items

See `docs/architecture/future-considerations.md`'s "Phase 6 additions":
full template/prompt authoring UI (richer than raw-JSON-via-REST), a real
`SpeechProfile`/`DiarizationProfile` database entity, per-organization
Processing Profiles/Templates, the reserved
`ModelProfilePurpose.DOCUMENT_GENERATION` field, tighter PromptVersion-to-
ProcessingProfile wiring, and generalizing contradiction detection beyond
`general_fact`.

## Git / PR / Merge Status

- Branch: `phase-6-templates-profiles`, off `main` at `2c13448`.
- PR: [#10](https://github.com/ley338-gif/VocaDox/pull/10) — "Phase 6:
  Templates & Profiles — Template Engine, Model/Processing Profiles,
  config hierarchy".
- Commits: `5d228d7` (Template Engine/Profiles/config hierarchy
  foundation), `9677b9c` (migration 0008 + domain tests), `f22a14a`
  (frontend admin surface + profile picker), `021c159`/`b239873`
  (OpenAPI drift root-cause + fix), `9408863`/`1f94361` (transitive
  license inventory regenerations), `ecd5248` (npm audit CI resilience).
- All 7 required GitHub Actions checks: **green** on both workflow runs
  for the final commit (`ecd5248`).
- **Merge: performed** (`5ecefc9`, regular merge commit on `main`,
  matching Phase 5's precedent). Verified `main` fast-forwarded to
  `5ecefc9` locally after merge. No open risk required product-owner
  escalation this phase — every merge-gate condition in the phase brief
  was independently verified: General and Meeting Processing Profiles
  genuinely differ end-to-end (both the automated test suite and a real
  Docker Compose deployment), template versioning is real (publish
  retires-not-deletes, past `DocumentRevision`s reference the exact
  version they used), the configuration hierarchy resolves and explains
  correctly across all three layers (verified live via HTTP against a
  real deployment, not just unit tests), existing Phase 4/5 functionality
  is unregressed (184/184 tests, including all 173 pre-existing),
  organization/permission authorization is enforced and tested, fresh
  install/migration/restart persistence were all validated against real
  infrastructure (not assumed), 0 blocked/0 unknown licenses, all CI
  green, and documentation is current.

## Recommendation

**GO for Phase 7.** VocaDox's extraction and document composition are now
genuinely configurable per conversation through a real three-layer
hierarchy with honest explainability, backed by a Template Engine that
demonstrably drives different behavior (not just a renamed switch) while
leaving every pre-Phase-6 conversation's behavior byte-identical. Three
real, unrelated CI-blocking issues (a fastapi/starlette version gap, a
stale OpenAPI baseline, and a compliance-inventory gap that briefly and
incorrectly looked like a blocked-license situation) were each root-caused
and fixed rather than worked around, and a fourth live external
flakiness (npm's audit endpoint) was mitigated with a bounded retry
rather than silently disabling the security check. No new open risk was
introduced.
