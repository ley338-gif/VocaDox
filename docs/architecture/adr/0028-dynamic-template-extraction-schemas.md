# 0028 — Template-defined extraction categories build Pydantic schemas dynamically

## Status
Accepted

## Context
Phase 4 hardcoded exactly 3 extraction categories
(`general_fact`/`decision`/`task`), each with its own hand-written
Pydantic schema class in `app.intelligence.schemas`
(`GeneralFactsExtraction`/`DecisionsExtraction`/`TasksExtraction`) used
both to build the JSON Schema handed to the LLM's structured-output mode
and to validate the raw response — spec §23/§24's "narrow, well-defined
schema per category, never one unconstrained prompt".

Phase 6 needs a real Template Engine where a template (e.g. "Meeting")
defines genuinely different categories/fields than "General" — but must
not require a code change (a new hand-written Pydantic class) every time
an admin authors a new template, or the Template Engine would not actually
be an engine, just a config switch between a fixed set of hardcoded
options.

## Decision
`app.templates.schema_builder.resolve_category` takes one
`TemplateVersion.extraction_categories[i]` JSON definition and produces
the exact same triple `(schema_cls, item_field, fact_type)` the Phase 4
code already worked with, via two paths:

- **`builtin: true`** resolves directly to the existing, unchanged
  `app.intelligence.schemas.EXTRACTION_CATEGORIES` entry (the identical
  Pydantic class object, not a re-implementation) — this is what keeps the
  seeded "general" template byte-for-byte behaviorally identical to Phase
  4/5 (same field constraints, same validation errors, same JSON Schema).
- **Anything else** is built at resolution time via `pydantic.create_model`
  from the category's `fields: [{name, max_length, description}]` list,
  always adding the same `certainty`/`evidence_segment_sequences` fields
  every category needs for the evidence-citation contract
  (`app.intelligence.service._resolve_evidence`) to keep working
  unmodified.

`app.intelligence.service.run_extraction` iterates
`resolve_categories(template_version.extraction_categories)` instead of
the module-level `EXTRACTION_CATEGORIES` dict directly, with
`template_version` defaulting to the "general" template's published
version when omitted (backward compatible for every pre-Phase-6 caller).

## Consequences
- A new template category is authored as data (a JSON category
  definition via `POST /api/v1/templates/{id}/versions`), not code — the
  actual Template Engine requirement.
- The dynamically-built classes are ephemeral (constructed fresh per
  extraction call, not cached/registered anywhere persistent) — cheap
  enough given extraction already makes one LLM round trip per category,
  and avoids any global-registry staleness risk if a template version is
  published/retired mid-process.
- `pydantic.create_model`'s typing is inherently dynamic;
  `app.templates.schema_builder` isolates the two `# type: ignore` sites
  needed for `mypy --strict`-adjacent checking rather than spreading them
  across `app.intelligence.service`.
- The "general" template's identity-preserving `builtin: true` path means
  `tests/intelligence/test_schemas.py` (which imports
  `GeneralFactsExtraction`/`DecisionsExtraction`/`TasksExtraction`
  directly) needed zero changes — verified by a dedicated identity
  assertion in `tests/templates/test_versioning.py` and the full Phase 4/5
  regression suite passing unchanged.
- A template author is trusted to write server-side JSON category
  definitions (an admin-only, `template:write`-gated action) — there is no
  sandboxing beyond ordinary Pydantic field validation (`max_length`,
  required-by-default). This is an acceptable trust boundary matching
  every other admin-only write path in the system (e.g. RBAC role
  assignment), not a new risk class.
