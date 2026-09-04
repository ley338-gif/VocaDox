# `app/templates/`

**Status: implemented (Phase 6).**

Template Engine domain (spec §42/§43): `Template`/`TemplateVersion` (never
mutated in place once published — publishing always creates a new version;
see `app.templates.models`), `Prompt`/`PromptVersion` (DRAFT -> TEST ->
PUBLISHED -> RETIRED lifecycle), and `app.templates.schema_builder` (turns
a template's JSON category definitions into real Pydantic extraction
schemas at runtime — either the exact builtin Phase 4/5 schemas for the
"general" template, or a genuinely template-defined dynamic schema for
"meeting" and the foundation-only "medical_consultation"/"psychotherapy"
templates).

See `docs/architecture/templates.md`, `PHASE_6_VALIDATION_REPORT.md`, and
`app.templates.seed` for the seeded initial templates/prompts.
