# 0004 — Evidence-first / three-layer data model (Source → Facts → Document)

## Status
Accepted (target architecture; not yet implemented — see Consequences)

## Context
VocaDox's core value proposition is *evidence-based* documentation: every
statement in a generated document must be traceable back to what was
actually said (or otherwise recorded) in a conversation, not silently
invented by an LLM. This requires the data model to keep provenance as a
first-class citizen rather than bolting it on after the fact.

## Decision
Adopt a three-layer provenance model, detailed in
`docs/architecture/domain-model.md`:

1. **Source** — the immutable raw material: transcript segments (with
   speaker + timing), user-supplied context, external system data, or
   manually entered notes. Tagged with one of four Evidence Types
   (`EVIDENCE_SPOKEN`, `EVIDENCE_USER_CONTEXT`, `EVIDENCE_EXTERNAL_SYSTEM`,
   `EVIDENCE_MANUAL`) plus an `UNVERIFIED` state for anything not yet
   reviewed.
2. **Facts** — discrete, structured claims extracted (by LLM or human) from
   one or more Sources, each fact carrying a link to the Source span(s) that
   support it (`fact_evidence`).
3. **Document** — the generated/composed output, where every
   document-level statement is traceable back through Facts to Source.

Example (spec §4): a spoken mention of "Ramipril 5mg" in a transcript
segment (Source, `EVIDENCE_SPOKEN`) becomes an `extracted_fact` (medication
= Ramipril, dose = 5mg) linked via `fact_evidence` to that transcript
segment, which is then referenced — not re-invented — when a Document
includes "Patient is on Ramipril 5mg."

## Consequences
- Every fact is auditable: a reviewer (or the `review` domain, once
  implemented) can always jump from a document statement back to the exact
  spoken words or context that justified it.
- This is materially more complex than a naive "LLM writes the document"
  approach, but it's the entire reason the product is trustworthy for
  clinical/compliance-sensitive use.
- Phase 0 does not create any of these tables (spec §65: domain schema
  starts Phase 1) — this ADR documents the target shape that Phase 1's
  `conversations`/`evidence`/`documents` migrations will implement.
