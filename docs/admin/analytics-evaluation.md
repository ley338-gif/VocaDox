# Analytics, Evaluation Lab & Model Lifecycle (Phase 8)

Implements the roadmap §73 Phase 8 items: technical analytics, quality
metrics, correction metrics, Evaluation Lab, model comparison, prompt
comparison, model lifecycle, pilot, rollback. Backend: `app.analytics`
(`models.py`/`fixtures.py`/`eval_engine.py`/`service.py`/`router.py`).
Frontend: `AdminAnalyticsPage.tsx`, `AdminEvaluationLabPage.tsx`, and the
Model Lifecycle panel added to `AdminProfilesPage.tsx`.

## Technical analytics — `GET /admin/analytics/technical`

Permission: `analytics:read`. Real aggregates over `ProcessingJob` rows
(the same Phase 3 table Phase 7's Jobs/Workers admin views already use —
no duplicate tracking table): job counts by type/status over a rolling
window (`days`, default 30), per-type success rate (succeeded /
(succeeded + failed) among terminal jobs), per-type average latency
(`completed_at - started_at` over SUCCEEDED jobs), and daily volume.

## Quality metrics — `GET /admin/analytics/quality`

Permission: `analytics:read`. Precisely-defined descriptive statistics,
never a fabricated accuracy score:

- **Transcript correction rate**: distinct corrected `transcript_segments`
  (via `transcript_segment_corrections`) / total segments.
- **Fact corrected-or-removed rate**: `extracted_facts` with
  `review_status` in (CORRECTED, REMOVED) / total facts. Explicitly NOT
  "AI accuracy" — a CONFIRMED fact could still be wrong if unreviewed, and
  PENDING facts haven't been reviewed at all.
- **Review issue resolution counts**: `review_issues.status` and
  `resolved_status` breakdowns.

## Correction metrics — `GET /admin/analytics/corrections`

Permission: `analytics:read`. Real analytics over the correction-feedback
audit trails (`transcript_segment_corrections` since Phase 3,
`fact_corrections` since Phase 5): correction-event counts by fact
category, most-corrected GENERAL_FACT subjects (e.g. "Ramipril"), total
segment-correction count. Per spec §38: read-only analytics, never fed
into a model-training pipeline — no such pipeline exists in this
codebase.

## Evaluation Lab — `/admin/evaluation/*`

Permission: `analytics:read` to view, `evaluation:run` to run a
comparison. Runs a synthetic fixture (`app/analytics/fixtures.py`,
`consultation_ramipril_v1` — a hand-authored German consultation scenario
with a deliberate self-contradiction, documented provenance, no real
person) through two real subjects and measures:

- **Facts matched** vs. a documented gold set (lenient substring
  matching — see Known Limitations).
- **Evidence linkage rate**: fraction of returned items whose
  `evidence_segment_sequences` resolve to a real fixture segment.
- **Contradictions detected** vs. expected (1 — the fixture's dose
  correction).
- **JSON schema validity** per category.
- **Latency** (wall-clock, real).

Two modes:
- `POST /admin/evaluation/model-comparison`: two `ModelProfile`s, same
  built-in system prompt/category instructions — isolates the model.
- `POST /admin/evaluation/prompt-comparison`: two `PromptVersion`s, same
  `ModelProfile` — isolates the prompt.

Every run is persisted (`evaluation_runs`) — `subject_a`/`subject_b` carry
only ids/config, `result_a`/`result_b` only counts/booleans (never
fixture/transcript text) — inspectable later via
`GET /admin/evaluation/runs[/{id}]`. A run that fails (e.g. provider
unreachable) is stored `status=failed` with `error_message_safe` set —
visible, never silently discarded.

**Real results**: see `PHASE_8_VALIDATION_REPORT.md` for an actual
Ollama `qwen2.5:14b` vs. `qwen3:14b` comparison run through this exact
mechanism, including the honest finding that `qwen3:14b` was NOT
compatible with the current `OllamaLLMProvider`'s `/api/generate`-based
prompting at these settings.

## Model Lifecycle — `/admin/model-profiles/{id}/lifecycle[-transition]`

Permission: `analytics:read` to view, `model-profile:promote` to
transition. Spec §51: `AVAILABLE -> TESTING -> PILOT -> PRODUCTION ->
RETIRED`, exactly one step forward at a time, enforced server-side
(`app.analytics.service.transition_model_lifecycle`). A forward
transition requires a complete admin-attested checklist
(`license_check`/`compatibility_check`/`benchmark`/`security_review`/
`admin_approval`, all `true`) — this is a structural enforcement of the
*process* (an admin must explicitly assert each step), not automated
verification of its content (see `app/analytics/service.py`'s module
docstring). `is_rollback: true` moves to ANY earlier status (including
reactivating a RETIRED profile back to AVAILABLE) with no checklist
required — a rollback is itself the safety mechanism.

Every transition — forward or rollback — writes a
`model_profile_lifecycle_events` row and nothing else in this codebase
ever changes `lifecycle_status`: there is no cron/background process that
can promote, retire, or roll back a model automatically.

## Permissions

| Endpoint | Permission |
|---|---|
| Technical/quality/correction analytics, evaluation run list/read, lifecycle read | `analytics:read` (Phase 1) |
| Run a model/prompt comparison | `evaluation:run` **(new)** |
| Model lifecycle transition (incl. rollback) | `model-profile:promote` **(new)** |

`analytics:read` already existed since Phase 1 (granted to Manager,
Auditor, System Admin) and already meant exactly "view analytics/
evaluation dashboards" — reused as-is, no redundant "read" permission
invented. `evaluation:run`/`model-profile:promote` are granted to Manager/
Template Manager/System Admin (see `app.identity.seed.ROLES`).

## Privacy

Every response above is structurally counts/ids/labels only — verified by
exact-key-set tests (`tests/analytics/test_privacy.py`), matching every
prior phase's admin-surface privacy discipline.
