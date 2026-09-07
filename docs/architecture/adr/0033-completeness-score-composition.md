# 0033 — Template completeness score: signal selection and composition

## Status
Accepted (2026-09-07). Post-GA, roadmap item P1-3.

## Context

The roadmap asks for a completeness indicator against a conversation's
Template: does it cover every required category, is every decision's
decision-maker and every task's owner named, plus speaking-share and
longest-monologue from diarization. Three design questions: (1) what
"decision rationale" maps to in the existing extraction schema, (2) how
to combine several unrelated signals into one score without penalizing a
conversation for lacking something it never had reason to contain, and
(3) how "longest monologue" is defined from raw diarization turns, which
carry no notion of "monologue" at all.

## Decision

**1. "Entscheidungsbegründung" maps to `DecisionItem.decided_by`, not a
new rationale field.** `app.intelligence.schemas.DecisionItem` captures
`description` and `decided_by` (who decided) but has no dedicated
reasoning/justification field — adding one would be an extraction-schema
change (prompt instructions, `schema_builder`, `FakeLLMProvider`,
`rendering.py`, every consumer of `structured_value`) well beyond this
measure's scope. `decided_by` is used as the completeness signal instead,
disclosed here as a known gap rather than silently reinterpreted: a
conversation can show "decision complete" while genuinely lacking a
recorded *reason* for the decision, only a *who*. A future measure that
wants true rationale tracking should extend `DecisionItem` deliberately,
informed by real usage of this simpler signal first.

**2. The overall score is an unweighted mean of whichever signals
actually apply.** Category coverage always applies (a template with zero
categories trivially scores 1.0, an edge case that can't occur for any
seeded template). Decision-owner and task-owner completeness are
included only when the conversation has at least one decision or task,
respectively — a conversation with no decisions isn't penalized for
lacking something it never had reason to record. Rejected alternative: a
fixed weighting (e.g. category coverage worth 50%) was considered and
dropped for the same reason ADR-0032 rejected a precisely calibrated
voiceprint threshold — no real usage data exists yet to justify one
weighting over another, and an unweighted mean of applicable signals is
easier to reason about and explain to a user than an opaque formula.

**3. "Longest monologue" is a heuristic: consecutive diarization turns
from the same detected speaker, tolerating up to 1.5s of silence between
them, count as one continuous span.** Diarization turns are per-utterance,
not per-"monologue" — a real speaker taking a breath mid-sentence
produces two turns with a small gap, and treating each as a separate
monologue would understate real speaking spans. 1.5s is a plausible
natural-pause length, not derived from any dataset (VocaDox has none for
this). Documented as a disclosed heuristic in `docs/user/completeness.md`
rather than presented as an exact measurement.

## Consequences

- No new dependency, no new persisted state, no new migration — the
  score is computed fresh on every `GET .../completeness` call from data
  that already exists (facts, diarization segments), matching
  `app.analytics.wer`'s "pure metric, not a generated statement" posture.
- Speaking-share/monologue metrics reuse `app.diarization.service
  .list_speakers`'s existing "only the active diarization run" scoping,
  so a reprocessed conversation's completeness view never mixes stale
  and current speaker data (see that function's own docstring for the
  regression this scoping originally fixed).
- If a future template gains many categories, or a conversation has very
  few facts, the score can look noisy (one category swing changes it by
  a large percentage). This is accepted as inherent to a live,
  transparently-composed indicator rather than a defect to smooth over
  with hidden weighting.
