# 0025 — Extraction category/schema design

## Status
Accepted

## Context
Spec §23/§24 requires `Transcript -> Structured Facts -> Evidence Mapping
-> Schema Validation -> Consistency Checks -> Contradictions -> Review
Issues`, explicitly never `Transcript -> "write a report" -> Document`.
The spec names Medication/Symptoms/Decisions/Tasks/Follow-Ups/General
Facts as *example* categories for a medical domain, but VocaDox's core
must not be hard-tuned to one domain (spec §1/§6) — domain-specific
categories belong in a future Template (Phase 6), not hardcoded here.

## Decision
Three domain-neutral-where-possible categories, each a narrow Pydantic
schema (`app.intelligence.schemas`), each requested from the LLM as a
**separate** structured-output call (never one shared prompt):

1. **`general_fact`** — a subject/attribute/value triple (e.g.
   `subject="Ramipril", attribute="dose", value="5mg"`, or
   `subject="Termin", attribute="date", value="Montag 10 Uhr"`). This
   shape subsumes the spec's "Medication"/"Symptoms"/general "General
   Facts" examples without hardcoding any of them as a fixed field set,
   AND is what makes contradiction detection (ADR-0026) possible
   generically: two facts with the same normalized (subject, attribute)
   and a different value are structurally comparable, no domain knowledge
   required.
2. **`decision`** — a concrete decision made during the conversation,
   with an optional `decided_by`.
3. **`task`** — covers both the spec's "Tasks" and "Follow-Ups" examples
   as one schema (`description`, `assignee`, `due_date`) — a follow-up is
   modeled as a task with a due date and no assignee, rather than
   introducing a fourth near-identical schema for Phase 4's scope.

Deferred: a fixed "Medication" schema with dedicated `dose`/`frequency`/
`route` fields, a fixed "Symptoms" schema — both would bake a medical
assumption into the core, which is explicitly out of scope until
Templates exist (Phase 6). `general_fact`'s triple shape covers the
Ramipril example the spec itself uses without that assumption.

## Uncertainty is a first-class schema concept, not an afterthought
Every category's `certainty` field is one of `stated | unclear |
incomplete | not_mentioned` (`app.intelligence.schemas.Certainty`), and
every optional string field's *value* may independently be the literal
`NOT_MENTIONED` — the system prompt (`app.intelligence.prompts
.SYSTEM_PROMPT`) explicitly instructs the model to use it instead of
guessing. Verified against a real model (not just documented as intent):
see PHASE_4_VALIDATION_REPORT.md's real-model validation, which shows
`NOT_MENTIONED` correctly returned for genuinely absent transcript
information, both in a synthetic negative-control transcript and in the
realistic multi-fact conversation.

## Evidence linking without evidence fabrication
Every extracted item carries `evidence_segment_sequences: list[int]` —
the transcript segment sequence number(s) the model claims support it
(the prompt renders the transcript as `[SEG n] text` lines so the model
can cite them back). `app.intelligence.service._resolve_evidence` treats
this list as an unverified claim: only sequence numbers that resolve to a
REAL segment of the transcript being extracted become `FactEvidence`
rows; anything else (a hallucinated/out-of-range number) is silently
discarded — never trusted, never surfacing as if it were real evidence. A
fact with zero resolved evidence becomes `FactStatus.UNVERIFIED` with a
`MISSING_EVIDENCE` review issue, not a dropped/fabricated result. This is
exercised by a real, run test:
`tests/intelligence/test_pipeline_extraction.py
::test_evidence_fabrication_is_never_trusted_and_missing_evidence_is_flagged`.

## Consequences
- Three LLM calls per extraction run (one per category) instead of one —
  more tokens/latency, but each call has a narrow, independently
  validated Pydantic schema, matching the spec's explicit modularity
  requirement over a single unconstrained prompt.
- Adding a fourth category later is additive (one more entry in
  `EXTRACTION_CATEGORIES`), not a breaking schema change to existing
  facts.
- `structured_value` is stored as JSON on `ExtractedFact` rather than a
  wide table with nullable per-category columns — consistent with how
  Phase 3 stored provider-native output (`ProcessingRun.raw_output`) and
  word timing (`TranscriptSegment.words`, ADR-0021).
