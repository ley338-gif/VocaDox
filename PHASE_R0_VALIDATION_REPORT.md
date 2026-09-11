# R0 (Research Roadmap) Validation Report — Diarization Eval Infrastructure

## Executive Summary

R0 is the first stage of a new, smaller post-GA research roadmap (R0-R3),
approved by the owner on 2026-09-12 under the standing autonomous GO
(`[[github-workflow-autonomy]]`) — same posture as the Stage P0-P3
competitive-roadmap reports (`PHASE_13_P*_VALIDATION_REPORT.md`): this
documents what shipped, how it was verified, and what remains honestly
open, not a Phase 0-12-style full hardening audit.

R0's job was narrow and infrastructural: Phase 12's GA validation report
disclosed Finding #12 — "genuine multi-voice diarization accuracy has
never been empirically verified anywhere in this project — every
'2-speaker' test fixture since Phase 3 used the same synthetic voice at
different playback rates, not two genuinely distinct voices." R0 builds
the local, provider-agnostic eval framework needed to actually close that
gap (DER/JER metrics, a fixture registry, a FastMSS-based real-fixture
generator), wires it into the existing Evaluation Lab as a first-class
quality record, and records the license disposition of the one new
dev-only tool involved.

**What R0 actually proves, and what it does not yet prove, matters more
than usual here — see "Concrete answer to the empirical question" below.**
The eval framework, its metric implementation, and its API/UI wiring are
built, unit-tested, and merged. Real, empirical, real-voice diarization
accuracy numbers (the thing that would fully close Finding #12) require a
FastMSS-generated batch scored against a real, locally-installed pyannote
pipeline — neither a speech corpus download nor a GPU/pyannote
installation was available in this session's sandbox (matching this
project's own established "admin explicitly installs real models" pattern
for pyannote/Ollama — never silently assumed). This is disclosed as an
explicit, actionable follow-up, not silently skipped.

**Recommendation: CONDITIONAL GO for R1.** R1 (Sortformer integration)
can begin immediately on the *implementation* side — the
`DiarizationProvider` interface this eval framework already targets needs
no changes for a second provider. Before R1's own validation report can
claim a real accuracy comparison between pyannote and Sortformer, someone
with the required environment (network access for a speech corpus, and
either GPU or patience for CPU inference) must run the
`tools/dev/fastmss/` runbook once and execute
`POST /admin/evaluation/diarization-accuracy` with
`VOCADOX_DIARIZATION_FIXTURES_DIR` pointed at that real batch and
`VOCADOX_DIARIZATION_PROVIDER=pyannote` — this is the one concrete
manual step standing between R0's infrastructure and an actual answer to
Finding #12.

## Scope

One PR, `research-r0-eval-infrastructure` branch:

| Area | What shipped |
|---|---|
| Metrics | `backend/app/analytics/diarization_metrics.py` — pure-stdlib DER (NIST RT-style, overlap-aware) and JER (Ryant et al. 2019), label-permutation-invariant |
| Ground truth | `backend/app/analytics/rttm.py` — RTTM parse/format |
| Fixtures | `backend/app/analytics/diarization_fixtures.py` — provider-agnostic fixture registry; bundled synthetic smoke set (`diarization_smoke_fixtures/`) + `VOCADOX_DIARIZATION_FIXTURES_DIR` override for a real batch |
| Eval runner | `backend/app/analytics/diarization_eval.py` — runs any `DiarizationProvider` against fixtures, aggregates DER/JER per fixture and per overlap level |
| Evaluation Lab integration | New `EvaluationRunType.DIARIZATION_ACCURACY`, `run_diarization_accuracy_eval` (service), `POST /admin/evaluation/diarization-accuracy` (router) — reuses the existing `EvaluationRun` table, no new one |
| Frontend | New "Sprechererkennung (DER/JER)" tab on `AdminEvaluationLabPage`, reusing design-system components |
| Dev tool | `tools/dev/fastmss/` — FastMSS orchestration script + overlap-ratio calibration helper + README (setup, license, runbook) |
| Compliance | `compliance/exceptions.yml` FastMSS entry (GPL-3.0, dev-only, never installed/vendored/distributed) |
| Docs | ADR-0047 (design decisions), `docs/architecture/diarization.md` cross-reference |

Out of scope (explicitly, per the R0 task): R1 (Sortformer integration),
R2 (second STT provider PoC), R3. Nothing in this PR adds a second
diarization or STT provider — only the measurement infrastructure a
second provider will be evaluated with.

## Concrete answer to the empirical question

The R0 task required confirming, before writing extraction code, that
generated fixtures "actually produce different diarization behavior... at
different overlap levels" — the empirical bar for "this actually fixes
Finding #12," not just "the tool ran." Two separate claims, kept
separate:

1. **Does the DER/JER *metric implementation* respond correctly to
   increasing overlap severity?** Yes — proven directly, not assumed.
   `backend/tests/analytics/test_diarization_metrics.py::test_der_increases_with_overlap_severity_for_a_realistic_hypothesis_degradation`
   constructs a hypothesis that mimics a real diarizer's known overlap
   weakness (reports exactly one active speaker during any period of true
   overlap — the exact `exclusive_speaker_diarization` failure mode
   `app/providers/diarization.py`'s own docstring warns against) against
   the project's three canonical overlap levels (none/some/heavy) and
   asserts `DER(none) < DER(some) < DER(heavy)` — it passes. A companion
   test proves JER catches a fully-missed quiet speaker that DER's
   time-weighting hides (`DER < 0.10` but `JER > 0.45` for the same case).
   The bundled smoke fixtures independently verify a clean 0%/25%/75%
   realized-overlap-ratio progression across their three files
   (`tools/dev/fastmss/report_overlap_ratio.py`, run against
   `diarization_smoke_fixtures/`).

2. **Does a *real* diarization provider (pyannote) actually show
   differentiated DER/JER on *real, genuinely-distinct-voice* audio at
   these overlap levels?** **Not yet answered — disclosed, not hidden.**
   This requires: (a) a real FastMSS batch, which requires downloading a
   speech corpus (e.g. LibriSpeech dev-clean) — no network access to fetch
   one was available in this environment; and (b) a locally-installed
   pyannote pipeline (gated on Hugging Face, requires a token and, per
   `docs/admin/model-installation.md`, an explicit admin install step,
   never something this codebase does automatically) — also unavailable
   here, and mandatory CI itself never installs the `ai` extra (see
   `.github/workflows/ci.yml`'s `backend` job), so this can never be
   proven in CI either, by design. `tools/dev/fastmss/README.md` is a
   real, complete, runnable runbook for whoever has that environment next.

Framing (1) as done and (2) as an open, actionable item is the honest
answer here — claiming (2) without actually running it would be exactly
the kind of rubber-stamped synthetic-fixture problem R0 exists to stop
happening again.

## Test / CI Summary

- Backend: full suite green (487 tests collected), ruff/mypy clean across
  213 source files (`ruff check .`, `mypy app`); R0 added 13 new tests to
  `tests/analytics/` (11 pure metric/eval-framework unit tests in two new
  files, `test_diarization_metrics.py` and `test_diarization_eval_framework.py`,
  + 2 new API-level Evaluation Lab tests in `test_evaluation_lab.py`),
  taking that package from 29 to 42.
- Frontend: `npm run typecheck` / `npm run lint` / `npm run test`
  (vitest, 64 passed) / `npm run build` all clean; new UI verified via
  typecheck/lint/build, matching this project's established
  "admin-page UI verified via typecheck/lint/build" precedent (Phase 12
  Finding #10) — no new Vitest suite added for the one new tab.
- `python compliance/check_licenses.py`: **PASS**, 0 blocked/0 unknown
  across direct (44), transitive (505), containers (6), and models (6) —
  unaffected by FastMSS, which never appears in any of the four scanned
  inventories (by design — see "License disposition" below).
- OpenAPI TS client regenerated from a real running backend
  (`frontend/openapi.json`, `frontend/src/api/generated/schema.d.ts`) to
  keep the drift-check CI job green.

## License Disposition

- **FastMSS** (https://github.com/popcornell/FastMSS): **GPL-3.0**,
  verified from the repository's own README/license statement, 2026-09-12.
  In `compliance/license-policy.yml`'s `blocked` bucket. Recorded as a
  **dev-only exception** in `compliance/exceptions.yml` (see that entry
  for the full reasoning) — never a pip/npm dependency
  (`backend/pyproject.toml` is unchanged by this PR for any extra), never
  vendored into this repository, never run in CI or any Dockerfile, never
  present in any shipped image (`compliance/container-inventory.yml` is
  unchanged — correctly has no FastMSS entry). Only its *output data*
  (synthesized meeting waveforms + RTTM ground-truth text) would ever
  touch a local, non-distributed fixture directory a developer points
  `VOCADOX_DIARIZATION_FIXTURES_DIR` at — nothing FastMSS-derived is
  committed to this repository. This is the same posture this project
  already gives Ollama: an external tool an admin/developer installs and
  runs themselves, never bundled.
- No other new dependency. `backend/app/analytics/diarization_smoke_fixtures/`
  contains this project's own tiny, self-generated (stdlib `wave`/`math`,
  `backend/scripts/generate_diarization_smoke_fixtures.py`) synthetic
  two-tone audio — not derived from FastMSS or any third-party corpus, and
  not real speech (see Known Limitations).

## Known Limitations / Assumptions (disclosed, not blocking merge of R0 itself)

1. **The empirical gap (Finding #12) is not yet fully closed** — see
   "Concrete answer to the empirical question" above. R0 ships the
   infrastructure and proves the metric implementation is sound and
   overlap-sensitive; it does not yet ship a real pyannote-vs-real-voice
   DER/JER number, because that requires a speech corpus download and a
   real pyannote install neither available in this session nor in CI by
   design. This is the single concrete gating item before R1's own
   validation report can claim a real pyannote-vs-Sortformer comparison.
2. **Bundled smoke fixtures are synthetic two-tone audio, not speech** —
   deliberately: they exist only to prove the framework's plumbing in
   mandatory CI (which has no GPU/`ai` extra), never presented as evidence
   about real-voice accuracy. `FakeDiarizationProvider` doesn't even read
   the audio file, so these fixtures also can't meaningfully be run
   through the real pyannote pipeline as a substitute — a real FastMSS
   batch is required for that.
3. **FastMSS batch's "none/some/heavy" mapping to `boost_overlap_factor`
   is a starting point** (0.0/1.0/3.0), not independently calibrated
   against a target overlap percentage — `tools/dev/fastmss/report_overlap_ratio.py`
   exists specifically so whoever generates the real batch confirms actual
   realized overlap before trusting the split, per ADR-0047/README.md.
4. **"German-ish" is not German** — FastMSS needs a lhotse-manifested
   speech corpus; the practical smallest real option (LibriSpeech) is
   English. No open German multi-speaker corpus was identified as readily
   available for this dev-only tool. This is a disclosed substitution,
   not a silent one — see `tools/dev/fastmss/README.md`.
5. **`subject_b`/second-provider comparison is reserved, not implemented**
   — `EvaluationRunType.DIARIZATION_ACCURACY` runs are always
   single-provider in R0 (`subject_b` is a `{"note": "reserved for R1"}`
   placeholder). R1 is expected to populate it for a real pyannote-vs-
   Sortformer run, reusing this exact run type.

## Findings Register

No process or product-correctness finding in the sense Stage P0's report
used the term (a CI-fix-and-repush cycle). The one real finding worth
recording explicitly: **the R0 task's initial framing assumed FastMSS uses
TTS to synthesize distinct voices — checking FastMSS's actual upstream
README before writing any extraction code (per this project's standing
"verify before building" discipline) found it does not use TTS at all; it
composites real, already-distinct human speaker recordings from an
existing corpus.** This was a better fit for closing Finding #12, not a
problem, and is recorded in ADR-0047 as the reason the fixture-source
design differs from the task's initial framing.

## Next

R1 (Sortformer integration): can start on the provider implementation
immediately — no changes needed to `DiarizationProvider`,
`app.analytics.diarization_eval`, or the Evaluation Lab wiring this PR
adds. Before R1's validation report claims a real accuracy comparison, run
the `tools/dev/fastmss/` runbook once (real speech corpus + real pyannote
install) and execute the diarization-accuracy Evaluation Lab run against
that real batch — the one open empirical step this report discloses
rather than skips.
