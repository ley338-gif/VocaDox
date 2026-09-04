# Templates, Prompts, Model Profiles, Processing Profiles (Phase 6)

Implements spec §17–§20/§42/§43. See `PHASE_6_VALIDATION_REPORT.md` for the
full validation narrative; this document describes the target-state
architecture the code actually implements.

## Template Engine (`app.templates`)

`Template` is a stable identity (`key`, e.g. `"general"`/`"meeting"`);
`TemplateVersion` is one immutable-once-published snapshot of its actual
content:

- `extraction_categories`: a JSON list of category definitions. Each is
  either `{"key": ..., "builtin": true}` (reuses one of
  `app.intelligence.schemas.EXTRACTION_CATEGORIES`'s exact Pydantic
  classes/instructions verbatim — this is how the **"General
  Conversation"** template stays byte-for-byte behaviorally identical to
  Phase 4/5's hardcoded categories) or a fully template-defined category
  (`fact_type`, `item_field`, `instruction`, `fields: [{name, max_length,
  description}]`), whose Pydantic schema `app.templates.schema_builder`
  builds dynamically via `pydantic.create_model` at extraction time. Every
  dynamically-built item still carries `certainty`/
  `evidence_segment_sequences` — the same evidence-citation contract every
  category must honor.
- `presentation`: an ordered list of `{category, title}` —
  `app.documents.service.compose_document` reads this instead of a
  hardcoded category→title mapping, so a document's section order/titles
  are template-driven, not fixed code.
- `review_rules`: reserved (nullable), not yet populated by any seeded
  template — a real future extension point, not a stub pretending to be
  used.

Publishing (`app.templates.service.publish_template_version`) never
mutates the previous published version's content — it flips its `status`
to `RETIRED` (frozen from that point on by a SQLAlchemy `before_update`
guard identical in spirit to `app.documents.models`'s revision-immutability
guard) and re-points `Template.current_published_version_id` at the new
one. Every past `ProcessingRun`/`DocumentRevision` that recorded a
`template_version_id` keeps resolving to its exact, unchanged content.

**Seeded templates** (`app.templates.seed`):

| key | status | categories |
|---|---|---|
| `general` | published v1 | `general_fact`/`decision`/`task` (builtin, = Phase 4/5) |
| `meeting` | published v1 | `agenda_topic`/`decision`(+rationale)/`action_item`(owner+due+priority) — genuinely different fields, not a renamed copy |
| `medical_consultation` | **draft only** | `symptom`/`medication`/`diagnosis` — foundation only per the brief |
| `psychotherapy` | **draft only** | `theme`/`intervention`/`goal` — foundation only per the brief |

The two draft-only templates are intentionally never published — no
`ProcessingProfile` can reference them (`get_published_version` raises),
an honest signal they are not real, selectable options yet.

## Prompts (`app.templates.models.Prompt`/`PromptVersion`)

Spec §43's lifecycle: `DRAFT -> TEST -> PUBLISHED -> RETIRED`. A
`PromptVersion` carries `system_prompt` + `category_instructions` (a
`{category_key: instruction_text}` map). One `Prompt` is seeded per
template (`extraction-general`, `extraction-meeting`, ...); the general/
meeting ones are published at seed time so
`ProcessingRun.prompt_version_id` has something real to reference from the
first extraction run.

`app.intelligence.service.run_extraction` accepts optional
`system_prompt`/`category_instruction_overrides` — when a
`ProcessingProfileVersion` names a `PromptVersion`,
`app.processing.orchestrator.execute_extract` passes its content through,
which genuinely changes the wording sent to the LLM (not just recorded for
provenance). When no `PromptVersion` is configured, the template's own
category instructions apply (still real, just not admin-overridden).

## Model Profiles (`app.profiles.models.ModelProfile`/`ModelProfileVersion`)

Extends Phase 4's minimal foundation into a real, versioned entity (spec
§18): `PATCH /api/v1/model-profiles/{id}` snapshots the pre-edit state
into a new `ModelProfileVersion` row before applying any change, so
`model_profile_versions` is a complete history of every state the profile
was ever in. `ModelProfilePurpose.DOCUMENT_GENERATION` is reserved
(spec's "different tasks may use different models") but **no runtime code
path ever calls an LLM for document composition** — see ADR-0027 and
`app.documents.service`'s module docstring, an explicit hard constraint
this phase does not relax.

## Processing Profiles (`app.profiles.models.ProcessingProfile`/`ProcessingProfileVersion`)

Spec §19's named, friendly preset bundling: Speech provider config +
Diarization provider config + Extraction Model (a `ModelProfile`) +
(reserved) Document Model + Template + Template Version + Prompt + Prompt
Version + Language + Retention Policy. "User sieht verständliche Namen.
Admin verwaltet technische Details" — `GET /api/v1/processing-profiles`
(readable by the standard `User` role) returns only `key`/`name`/
`description`/`is_system_default`, never the technical composition; the
admin-only version endpoints expose the full bundle.

Speech/Diarization remain `Settings`-driven configuration (a small JSON
hint column, not a real FK) — a full `SpeechProfile`/`DiarizationProfile`
DB entity is still Phase 7 (`docs/architecture/model-management-foundation.md`),
an honest, documented scope boundary rather than an oversight.

**Seeded processing profiles**: `general` (`is_system_default=true`,
template=general) and `meeting` (template=meeting), both published v1,
both referencing the seeded extraction `ModelProfile`.

## Configuration Hierarchy (`app.profiles.resolver`)

Spec §20: `SYSTEM DEFAULT -> PROCESSING PROFILE -> CONVERSATION OVERRIDE`.
`resolve_effective_config(session, conversation)` is the one place any
caller resolves "what configuration actually applies here":

1. **SYSTEM DEFAULT** — the one `ProcessingProfile` with
   `is_system_default=true` (seeded as `general`).
2. **PROCESSING PROFILE** — if `conversation.processing_profile_id` names
   a profile with a published version, every field is overridden from
   that version instead.
3. **CONVERSATION OVERRIDE** — `conversation.config_overrides` (a JSON
   object keyed by the same field names) overrides individual fields on
   top of whichever of the first two layers won — a per-field override,
   never a wholesale profile replacement.

`EffectiveConfig.field_sources`/`.explain()` records, per field, which
layer actually set the winning value — the explainability spec §20
explicitly requires. `GET /api/v1/conversations/{id}/effective-config`
exposes this; `PATCH /api/v1/conversations/{id}/config-override` writes
layer 3.

Wired into:
- `app.processing.orchestrator.execute_extract` — resolves the template
  version, extraction `ModelProfile`, and prompt version to actually use;
  records all three ids on the `ProcessingRun` for reproducibility (spec
  §43), falling back to Phase 4's `get_active_profile()`-only behavior if
  no system-default `ProcessingProfile` exists yet (e.g. mid-upgrade
  before the Phase 6 seed has run).
- `app.documents.service.compose_document` — resolves the template
  version for section presentation; records `template_version_id` on the
  `DocumentRevision`.

## Backward Compatibility with Phase 4/5

- `app.intelligence.service.run_extraction`'s new `template_version`/
  `system_prompt`/`category_instruction_overrides` parameters all default
  to `None`, resolving to the "general" template's published version and
  its unchanged wording — every pre-Phase-6 caller (including existing
  Phase 4 tests) is unaffected.
- The "general" template's `extraction_categories` reference
  `EXTRACTION_CATEGORIES`'s exact, unchanged Pydantic classes (`builtin:
  true`) rather than a reimplementation — verified by an identity check
  (`resolve_category(...).schema_cls is GeneralFactsExtraction`).
- `app.documents.service.compose_document`'s rendering for the 3 builtin
  categories (`general_fact`/`decision`/`task`) is unchanged when a fact's
  `structured_value` keys match exactly what those categories always
  produced; only a genuinely different category (e.g. Meeting's
  `action_item`) falls through to the new generic "field: value" renderer.
- Every new column (`conversations.processing_profile_id`/
  `config_overrides`, `processing_runs.template_version_id`/
  `prompt_version_id`/`processing_profile_version_id`,
  `document_revisions.template_version_id`,
  `model_profiles.thinking_mode`/`configuration`) is additive/nullable —
  see `alembic/versions/0008_templates_profiles.py`.
