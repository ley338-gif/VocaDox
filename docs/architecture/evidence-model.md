# Evidence model (Phase 4)

## The non-negotiable chain

`docs/architecture/domain-model.md`'s "Source -> Facts -> Document
provenance" section is the agreed target; Phase 4 makes the first two
layers real:

```
Conversation -> SourceMedia/Transcript -> ProcessingRun -> TranscriptSegment(s)
                                                                  |
                                                          FactEvidence
                                                                  |
                                                          ExtractedFact
```

`ExtractedFact.processing_run_id` points at the `ProcessingRun
(run_type=EXTRACTION)` that produced it; `FactEvidence` rows link it to
the specific `TranscriptSegment`(s) (by real database id, not a copied
timestamp/text snapshot) that justify it. A document (Phase 5, not built
here) would extend this chain one layer further, never skip it.

## `fact_evidence.evidence_type`

Uses the same four real evidence types documented in
`docs/architecture/domain-model.md` — Phase 4 only ever writes
`EVIDENCE_SPOKEN` (every fact here derives from a transcript segment).
`EVIDENCE_USER_CONTEXT`/`EVIDENCE_EXTERNAL_SYSTEM`/`EVIDENCE_MANUAL`
remain reserved for future evidence sources (user-supplied context
fields, integrations, manual reviewer entry) — no Phase 4 code path
produces them.

## A fact with no evidence is never dropped or fabricated

`ExtractedFact.status` is `FactStatus.UNVERIFIED` whenever zero
`FactEvidence` rows could be resolved for it — the fact still exists,
still visible via the API, just honestly marked. This is not a
theoretical guarantee: `app.intelligence.service._resolve_evidence` only
ever creates a `FactEvidence` row for a segment sequence number that
actually exists in the transcript being extracted; an LLM-claimed
sequence number that doesn't resolve is silently discarded, never
"repaired" into a plausible-looking link. See
`tests/intelligence/test_pipeline_extraction.py
::test_evidence_fabrication_is_never_trusted_and_missing_evidence_is_flagged`
and the real-model validation transcript in
PHASE_4_VALIDATION_REPORT.md.

## Evidence jump/highlight (frontend)

`GET /conversations/{id}/facts/{fact_id}/evidence` denormalizes each
linked segment's `sequence`/`start_ms`/`end_ms`/text onto the response
(`app.intelligence.api_schemas.FactEvidenceResponse`) so the frontend can
jump to/highlight the exact transcript moment in one round trip, reusing
the audio-sync pattern Phase 3 already built for transcript playback —
see `docs/user/facts-and-evidence.md`. This is a minimal, honest surface,
not the full Phase 5 two-column DOCUMENT/EVIDENCE Evidence UX.

## Authorization

Facts, evidence, and review issues are exactly as sensitive as the
transcript they derive from — every read goes through
`app.conversations.authz.authorize_conversation_access` with a dedicated
permission code (`fact:read`/`evidence:read`/`review-issue:read`), which
enforces Permission + Organization Membership + the Conversation's
Organization and returns 404 (never 403) for cross-organization access,
identical to every other Phase 2/3 resource. Heavily tested — see
`tests/intelligence/test_pipeline_extraction.py
::test_cross_organization_facts_and_evidence_return_404`.

## What's NOT built here

Document generation from facts, the Evidence UX (two-column layout,
"Warum steht das hier?" panel), correction/approval of facts — all built
in Phase 5, see `docs/architecture/documents.md`. `EVIDENCE_USER_CONTEXT`/
`EVIDENCE_EXTERNAL_SYSTEM`/`EVIDENCE_MANUAL` remain reserved for future
evidence sources not yet produced by any phase's code.
