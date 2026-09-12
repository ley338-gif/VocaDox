# R1 (Research Roadmap) Validation Report — Sortformer, a Second Diarization Provider

## Executive Summary

R1 is the second stage of the post-GA research roadmap (R0-R3), approved by
the owner on 2026-09-12 under the standing autonomous GO
(`[[github-workflow-autonomy]]`) — same posture as R0's own report: this
documents what shipped, how it was verified, and what remains honestly
open, not a Phase 0-12-style full hardening audit.

R1's job, per R0's own "Next" section: add a second, real
`DiarizationProvider` — NVIDIA NeMo's Streaming Sortformer 4-Speaker v2 —
so R0's DER/JER eval framework has more than one real provider to compare
`pyannote.audio` against, closing the rest of Phase 12's Finding #12
("genuine multi-voice diarization accuracy has never been empirically
verified"). R0 predicted this would need no changes to `DiarizationProvider`
or the Evaluation Lab wiring — **confirmed true**: `SortformerDiarizationProvider`
implements the exact same interface `PyannoteDiarizationProvider` does, and
`app.core.ai_providers.get_diarization_provider` (the one factory
`Depends()`-injected into both the diarization worker and the Evaluation
Lab's `POST /admin/evaluation/diarization-accuracy` endpoint) now
recognizes `VOCADOX_DIARIZATION_PROVIDER=sortformer` alongside the existing
`fake`/`pyannote` values.

**What R1 actually proves, and what it does not, matters as much here as it
did for R0 — see "Concrete answer to the empirical question" below.** The
provider implementation, its license disposition, and its wiring into the
existing eval mechanism are built and merged. Real, empirical DER/JER
numbers comparing pyannote against Sortformer on real, genuinely-distinct
voices — the thing that would fully close Finding #12 — require: (a) a real
FastMSS-generated fixture batch (R0's own open item, still open), (b) a
real, locally-installed pyannote pipeline (also still open from R0), AND
now additionally (c) a real, locally-installed Sortformer `.nemo`
checkpoint plus a working `nemo_toolkit` install. None of (a), (b), or (c)
were available in this session's sandbox — no GPU, no speech-corpus
network download budget, no admin-provided Hugging Face token, and no
multi-GB `nemo_toolkit` install were performed. This is disclosed as an
explicit, actionable follow-up, exactly like R0's own equivalent gap, not
silently skipped or assumed passing.

**Recommendation: CONDITIONAL GO for R2** (second STT provider PoC) — see
"Recommendation for R2" below for the exact condition, which mirrors R0's
own conditional GO for R1.

## Scope

One branch, `research-r1-sortformer-diarization`:

| Area | What shipped |
|---|---|
| Provider | `backend/app/providers/diarization.py` — `SortformerConfig` + `SortformerDiarizationProvider`, a second real `DiarizationProvider` wrapping NVIDIA NeMo's `SortformerEncLabelModel` |
| Wiring | `app.core.ai_providers.get_diarization_provider` accepts `VOCADOX_DIARIZATION_PROVIDER=sortformer`; `Settings.diarization_sortformer_model_dir_name` keeps its installed checkpoint in a separate `model_volume_root` subdirectory from pyannote's |
| Install | `app/cli/install_models.py`'s new `diarization-sortformer` `ModelProfile` (single `.nemo` file, `allow_patterns`-restricted, `requires_token=False`); `ModelProfile.allow_patterns` added as a new, generally-reusable field |
| Dependency | `backend/pyproject.toml`'s `[ai]` extra gains `nemo_toolkit[asr]>=2.0,<3.0`; `uv lock` re-resolved successfully (245 packages for this extra, up from ~165) |
| Compliance | `compliance/model-inventory.yml` — a real model entry (not a `compliance/exceptions.yml` dev-tool exception, since this ships in the product) |
| Docs | ADR-0048 (full decision record, including the model-card-vs-HF-API gating discrepancy), `docs/admin/model-installation.md`, `docs/architecture/diarization.md` cross-references, `deploy/compose.dev.yml` comment |
| Frontend | `AdminDiarizationPage.tsx` — small provider-discoverability note (Card + Badges), reusing existing design-system components; no new API field needed since `DiarizationProviderStatus` was already provider-agnostic |
| Tests | `backend/tests/test_sortformer_provider.py` (4 new tests: not-installed/installed status, clear error when unloaded, factory selection) + `test_architecture_boundaries.py` updated to include `SortformerDiarizationProvider` in the "domain code must not import concrete providers" check |

Out of scope (explicitly, per the R1 task): a combined single-run
pyannote-vs-Sortformer comparison (`EvaluationRun.subject_b` stays R0's
`{"note": "reserved for R1"}` placeholder — comparison today means two
separate runs, one per provider, compared by hand), R2 (second STT
provider PoC), R3.

## Concrete answer to the empirical question

Two separate claims, kept separate, exactly as R0's report did:

1. **Does `SortformerDiarizationProvider` conform to the
   `DiarizationProvider` interface and integrate cleanly with the existing
   eval/factory wiring, with no changes needed elsewhere?** **Yes — proven
   directly.** `get_diarization_provider()` constructs it correctly for
   `VOCADOX_DIARIZATION_PROVIDER=sortformer` (test:
   `test_get_diarization_provider_selects_sortformer`); its `status()`/
   `diarize()` not-installed paths raise the same
   `DiarizationModelUnavailableError` contract
   `PyannoteDiarizationProvider` does (3 passing tests); `uv lock` resolved
   the new `nemo_toolkit[asr]` dependency successfully against the existing
   CPU-pinned torch/torchaudio/torchcodec constraint with no conflicts (245
   packages, verified `uv lock --check` passes); ruff/mypy/the full
   backend test suite (491 tests collected — 487 from R0 + 4 new — 490
   passed, 1 pre-existing skip, same skip as before this PR) and the
   frontend's typecheck/lint/test(64 passed)/build all pass clean in this
   session.

2. **Does real Sortformer inference actually produce differentiated,
   correct diarization output on real audio, and does it actually compare
   meaningfully against pyannote's real DER/JER numbers?** **Not answered —
   disclosed, not hidden, exactly like R0's equivalent gap.** This requires
   all of:
   - A real, working `nemo_toolkit` install (multi-GB, ~80 additional
     transitive packages — `uv lock` succeeded, but a full `uv sync
     --extra ai` install and `docker build -f backend/worker.Dockerfile`
     were NOT attempted in this session: the resulting install/image is
     large enough that a real attempt risked consuming this session's
     remaining time/bandwidth budget without a clear path to also
     completing R1's other scope items, and — unlike a resolver check —
     a partial or interrupted multi-GB install would leave no useful
     partial evidence).
   - A real, downloaded `.nemo` checkpoint (verified download mechanics —
     the HF API's own file listing and `sha`/`gated` fields — but the
     actual `docker compose run --rm model-manager install
     diarization-sortformer` was never executed against a live model
     volume in this sandbox).
   - A real FastMSS-generated speech-corpus batch and a real pyannote
     install — R0's own still-open item, unchanged by this PR.

   `tools/dev/fastmss/README.md` (from R0) remains the real, runnable
   runbook; nothing about it needed to change for R1. The one *new*
   manual step R1 adds on top of R0's: after that runbook produces a real
   fixture batch and pyannote is really installed, an admin/developer
   additionally runs `docker compose run --rm model-manager install
   diarization-sortformer` (no token needed, unlike pyannote) and
   `POST /admin/evaluation/diarization-accuracy` a second time with
   `VOCADOX_DIARIZATION_PROVIDER=sortformer` — comparing that run's
   `EvaluationRun.result_a` against the pyannote run's is, today, a manual
   "compare two rows" step (see ADR-0048's "Not done in R1").

Framing (1) as done and (2) as an open, actionable item is the honest
answer here — exactly the discipline R0 established and R1 continues.

## Test / CI Summary (local, this session)

- Backend: full suite green — 491 tests collected (487 from R0 + 4 new in
  `test_sortformer_provider.py`), 490 passed, 1 skipped (pre-existing, not
  introduced by this PR), `ruff check .` and `mypy app` both clean across
  now-updated source files.
- `uv lock` (backend): re-resolved cleanly with `nemo_toolkit[asr]>=2.0,<3.0`
  added to the `[ai]` extra — 245 total packages for that extra (up from
  ~165 before this PR); `uv lock --check` confirms the committed lockfile
  matches `pyproject.toml`. No `nvidia-cublas`/`nvidia-cudnn` GPU-runtime
  binary packages appear in the resolution (torch/torchaudio/torchcodec
  stay pinned to the existing `pytorch-cpu` index) — NeMo's own
  `cuda-bindings`/`cuda-pathfinder` transitive deps are lightweight Python
  bindings, not multi-GB downloads.
- Frontend: `npm run typecheck` / `npm run lint` / `npm run test` (vitest,
  64 passed, unchanged from R0 — no new suite needed for one static info
  card) / `npm run build` all clean.
- **NOT run in this session** (disclosed, not silently skipped):
  - `docker build -f backend/worker.Dockerfile` with the new `nemo_toolkit`
    dependency actually present — the mandatory CI job that does this
    (`.github/workflows/ci.yml`) will run it for real once this PR is
    opened; this is the first genuine test of whether the full `[ai]`
    extra actually installs and the worker image actually builds with
    NeMo in it. This is real risk this report does not paper over: a
    resolver succeeding is not the same as a real multi-stage Docker build
    succeeding, and this project's own history (ADR-0017's torchaudio/
    torchcodec findings) shows resolver-level success has previously
    still hidden real import/runtime failures.
  - `compliance/generate_transitive_inventory.py` — **not** re-run in this
    session. Its own docstring requires the raw pip-licenses scan to run
    on Linux (several resolved packages are platform-conditional between
    this session's Windows sandbox and the `ubuntu-latest` CI runner), so
    a locally-regenerated file would not match what CI's own compliance
    job produces and would risk committing an inaccurate transitive
    license classification for ~80 new packages. `compliance/
    dependency-inventory-transitive.yml` is therefore left as R0 committed
    it; CI's compliance job (which regenerates this file on Linux and
    fails on either drift or a genuinely blocked/unknown license) is
    expected to fail on this PR's first run, and is the plan of record for
    discovering and fixing the real classification — via targeted
    follow-up commits to `PACKAGE_LICENSE_OVERRIDES`
    (`compliance/generate_transitive_inventory.py`) or, if warranted, a
    `compliance/exceptions.yml` entry — not a guess made from this sandbox.
  - `python compliance/check_licenses.py` — not re-run locally for the
    same reason (it reads the transitive file above, which was not
    regenerated here).
  - `frontend/openapi.json` / generated TS client — not regenerated;
    unaffected by this PR (no backend response schema changed — the
    diarization overview endpoint was already `Record<string, unknown>`
    on the frontend side and provider-agnostic on the backend, so no
    OpenAPI drift is expected).

**This report's CI section will be updated with the real outcome of the
worker Docker build and compliance job once this PR's CI actually runs —
see the PR itself for the final, authoritative CI status; this document
was written and committed alongside the implementation, not after
confirming a fully green run.**

## License Disposition

- **`nvidia/diar_streaming_sortformer_4spk-v2` (model weights)**: **CC BY
  4.0**, verified from TWO independent sources: (1) the model card's own
  "License Information" section; (2) directly against the Hugging Face
  model API (`gated: false`, `license: "cc-by-4.0"`, `sha:
  "5240a64075176943f677d30fa2171c780229f341"`), 2026-09-12. Not gated.
  Commercial use and redistribution permitted with attribution to NVIDIA.
  A real ambiguity is recorded rather than silently resolved: the model
  card's own usage sample mentions needing a Hugging Face token, which
  the HF API's `gated: false` field contradicts as an actual terms-gate —
  see ADR-0048 for the full reasoning and the stop-condition this project
  applies if that assumption turns out wrong in practice.
- **`nemo_toolkit` (runtime library, PyPI)**: **Apache-2.0**, verified via
  `raw.githubusercontent.com/NVIDIA/NeMo/main/LICENSE`
  ("Apache License Version 2.0, January 2004"), 2026-09-12. Verified
  SEPARATELY from the model-weight license, per this project's standing
  model-inventory discipline (never assumed identical).
- **Recorded in `compliance/model-inventory.yml`** as a real model entry
  (`bundled_with_product: false`, `downloaded_at_install: true`,
  `approval_status: approved`) — **not** a `compliance/exceptions.yml`
  dev-tool exception, unlike R0's FastMSS: Sortformer is a real,
  admin-installable, shippable production provider (selectable via
  `VOCADOX_DIARIZATION_PROVIDER`), not a developer-only test-fixture tool,
  so it gets the same inventory treatment `pyannote/speaker-diarization-3.1`
  and its dependent repos already have.
- **`nemo_toolkit`'s own ~80-package transitive dependency tree**: license
  classification genuinely unknown as of this report — see "NOT run in
  this session" above. This is the one real, disclosed compliance gap R1
  leaves open, with a concrete named mechanism (CI's compliance job +
  targeted override commits) to close it, not a silent assumption that it
  will be fine.

## Known Limitations / Assumptions (disclosed, not blocking merge of R1 itself)

1. **No real end-to-end Sortformer inference was executed** — no GPU, no
   `nemo_toolkit` install, and no real `.nemo` download in this sandbox.
   `SortformerDiarizationProvider.diarize()` follows the model card's
   documented usage pattern (`SortformerEncLabelModel.restore_from()` +
   the streaming-config attributes + `.diarize(audio=[path])`) as
   faithfully as possible but is unverified end-to-end. This mirrors
   exactly how `PyannoteDiarizationProvider` was first disclosed before
   Phase 3.1 closed the gap with a real token and a real install.
2. **The pyannote-vs-Sortformer DER/JER comparison itself was not run** —
   this requires closing R0's still-open item (real FastMSS batch + real
   pyannote install) AND additionally installing a real Sortformer
   checkpoint. See "Concrete answer to the empirical question" above for
   the exact remaining manual steps.
3. **The worker Docker image build with `nemo_toolkit` was not attempted
   locally** — `uv lock` resolved cleanly, which is real, positive
   evidence, but is not the same guarantee a full `docker build -f
   backend/worker.Dockerfile` gives. This PR's CI run is the first real
   test of that; if it fails, the plan is to fix it with real, targeted
   follow-up commits (pin adjustments, extra system packages NeMo may
   need at build time, etc.), the same iterative-CI-fix discipline this
   project's own git history already demonstrates (e.g. ADR-0017's
   real-build-driven 3.x->4.x pyannote pin reversal).
4. **`compliance/dependency-inventory-transitive.yml` was not regenerated**
   — see "Test/CI Summary" and "License Disposition" above for the full
   reasoning and the concrete plan (CI's own Linux-based compliance job +
   follow-up commits) to close this before merge.
5. **No combined two-provider `EvaluationRun`** — `subject_b` stays R0's
   reserved placeholder; comparing providers today means two separate
   Evaluation Lab runs (switch `VOCADOX_DIARIZATION_PROVIDER`, re-run),
   compared by hand. A genuine side-by-side comparison endpoint would be a
   reasonable future enhancement, not claimed as done here.
6. **Sortformer's embedding/confidence gaps versus pyannote are permanent,
   not temporary** — no per-speaker voice-embedding extraction API and no
   per-turn confidence score are documented on this model card (see
   ADR-0048). Voiceprint suggestion (ADR-0032) and any UI relying on
   per-turn confidence simply have no signal when Sortformer is the
   configured provider — this degrades the same way a failed per-turn
   pyannote embedding extraction already does (never a hard failure), but
   is a structural difference between the two providers' output richness,
   not a bug to fix later.

## Findings Register

No process or product-correctness finding in the Stage P0/R0 sense (a
CI-fix-and-repush cycle) — this report is written before this PR's CI has
actually run, so any such finding from a real CI failure will be recorded
as a follow-up commit's message instead, per this project's standing
"commit incrementally, poll CI, fix for real" discipline, not retrofitted
into this document's initial text.

The one real finding worth recording explicitly: the R1 task's framing
initially treated Sortformer as presumptively license-clean based on the
research letter's summary alone — checking the Hugging Face model API
directly (not just the model card's prose) surfaced the gating-language
discrepancy described in ADR-0048's "Decision" section (the usage sample
mentions a token; the API's own `gated` field says `false`). This is
recorded as a real, disclosed ambiguity rather than silently resolved
either way, consistent with this project's "verify before building"
discipline (the same discipline that drove ADR-0017's pyannote 3.x->4.x
pin reversal and R0's FastMSS-is-not-TTS correction).

## Recommendation for R2

**CONDITIONAL GO for R2** (second STT provider PoC), same conditional
structure R0 gave R1:

R2 can begin immediately on the *implementation* side — nothing about R1
changes the STT provider interface, and R0/R1's eval-framework pattern
(provider-agnostic interface + factory-based selection +
`VOCADOX_<X>_PROVIDER` env var) is now proven twice (pyannote/Sortformer
for diarization) as a repeatable shape a second STT provider can follow
directly. Before an R2 validation report can claim anything about *real*
STT accuracy differences between providers, the same concrete manual step
R0 named and R1 did not close still stands: someone with a real
environment (network for a speech corpus, GPU or CPU patience, and any
provider-specific credentials) needs to actually install and run the real
providers this eval framework was built to compare. R1 adds one further
recommendation on top of R0's: before that person's time is spent, budget
realistically for the fact that adding a real ML provider's dependency
tree (this PR's `nemo_toolkit` addition, ~80 new transitive packages) is
itself nontrivial CI/compliance work, not just a code-level integration —
R2's own second STT provider should expect the same.
