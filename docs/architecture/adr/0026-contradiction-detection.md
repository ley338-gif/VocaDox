# 0026 — Contradiction detection approach

## Status
Accepted

## Context
Spec §26 requires that when two facts conflict, a
`POTENTIAL_CONTRADICTION` review issue is created referencing both source
facts — the system must never auto-resolve which one is "true". This
needs to be a real, testable rule, not a documentation-only concept.

## Decision
A narrow, deterministic rule over `general_fact` facts only (see
ADR-0025 for why that category's subject/attribute/value shape exists):
two `GENERAL_FACT` facts in the same conversation, with the same
case/whitespace-normalized `(subject, attribute)` pair, whose normalized
`value` differs, are a contradiction
(`app.intelligence.contradictions.detect_contradictions`). This is
exactly the shape of the spec's own worked example — Ramipril's dose
stated as 5mg in one place and 10mg (or an escalation plan) in another.

Explicitly rejected alternatives:
- **Fuzzy text-similarity across arbitrary fact types** (decisions,
  tasks) — no principled, testable definition of "conflicting" exists for
  free-text descriptions without NLP machinery Phase 4 has no budget for;
  deferred rather than shipped as a low-confidence heuristic.
  `docs/architecture/future-considerations.md` records this as a
  candidate for a future phase (e.g. embedding-similarity-based
  contradiction detection once a document/review workflow exists to
  consume graded-confidence signals).
- **LLM-judged contradiction detection** (asking the model itself "do
  these two facts conflict?") — rejected because it reintroduces exactly
  the `LLM -> Truth` pattern the spec's core principle forbids; a
  structural, code-level rule is auditable and deterministic in a way an
  LLM judgment call is not.

## Never auto-resolved
`detect_contradictions` returns pairs of fact ids; the caller
(`app.intelligence.service.run_extraction`) creates exactly one
`ReviewIssue(issue_type=POTENTIAL_CONTRADICTION, related_fact_ids=[a, b])`
per pair, `severity=HIGH`. Neither fact's `status` is changed as a result
— both remain independently `VERIFIED`/`UNVERIFIED` per their own
evidence, exactly as extracted. A human reviewer (Phase 5's review
workflow, not built here) decides which value is correct, if either.

## Cross-run detection
The check runs against every non-`SUPERSEDED` `general_fact` fact for the
conversation (not just the current extraction run's newly-created facts),
so a contradiction between today's re-extraction and a fact from an
earlier run is still caught — re-extraction never silently drops the
original fact, matching Phase 3's "processing history is never destroyed"
precedent for reprocessing.

## Verification
- Unit tests: `tests/intelligence/test_contradictions.py` (same
  subject/attribute + different value -> contradiction; same value -> no
  contradiction; different subjects -> no contradiction; non-general-fact
  categories ignored; N-way conflicts produce the correct pairwise count
  with no duplicates).
- Integration test:
  `tests/intelligence/test_pipeline_extraction.py
  ::test_evidence_fabrication_is_never_trusted_and_missing_evidence_is_flagged`
  asserts a real `ReviewIssue(POTENTIAL_CONTRADICTION)` row is created and
  references both fact ids.
- **Real-model validation**: a real Ollama/Qwen2.5:14b extraction run
  against a synthetic conversation containing a genuine Ramipril
  dose-escalation contradiction (5mg then "increase to 10mg") produced
  exactly the expected `POTENTIAL_CONTRADICTION` review issue — see
  PHASE_4_VALIDATION_REPORT.md.
