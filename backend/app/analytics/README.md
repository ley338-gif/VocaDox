# `app/analytics/`

**Status: implemented, Phase 8.**

Technical analytics, quality metrics, correction metrics, the Evaluation
Lab (model + prompt comparison against a synthetic fixture), and Model
Lifecycle transitions (spec §50/§51, roadmap §73). See
`docs/admin/analytics-evaluation.md` for the full reference and
`PHASE_8_VALIDATION_REPORT.md` for what was actually verified.

No new domain data model beyond `ModelProfileLifecycleEvent` and
`EvaluationRun` (`models.py`) — technical/quality/correction analytics are
computed on read directly from tables that already existed
(`processing_jobs`, `transcript_segment_corrections`, `fact_corrections`,
`review_issues`), matching Phase 7's "no duplicate tracking table"
precedent for admin surfaces built over prior phases' data.

Never a training/fine-tuning pipeline (spec §38 hard rule) — every
function in this package only ever *reads* existing data or *calls* an
LLM provider's existing inference API to measure it.
