# R2 (Research Roadmap) Validation Report — Nemotron, a Second STT Provider (PoC)

## Executive Summary

R2 is the third stage of the post-GA research roadmap (R0-R3), approved by
the owner on 2026-09-12 under the standing autonomous GO
(`[[github-workflow-autonomy]]`) — same posture as R0's and R1's own
reports: this documents what shipped, how it was verified, and what
remains honestly open, not a Phase 0-12-style full hardening audit.

R2's job, per R1's own "Recommendation for R2": add NVIDIA's Nemotron 3.5
ASR Streaming 0.6B as a second, real `SpeechToTextProvider` alongside
`faster-whisper`, following the exact same shape R0/R1 proved twice for
diarization (provider-agnostic interface + factory-based selection via a
`VOCADOX_<X>_PROVIDER` env var + a real model-inventory license entry).

**The centerpiece of this report is the license research, done first,
before any integration code**, because Nemotron ships under
**OpenMDW-1.1**, a license this project had never evaluated before
(faster-whisper is MIT, pyannote is MIT, Sortformer is CC BY 4.0,
Ollama/Qwen is Apache-2.0). The full license text
(`https://openmdw.ai/license/1-1/`) was fetched and read directly — not
assumed equivalent to a standard permissive license from a research
summary's "weights available" framing. **Finding: no genuine
license-policy blocker.** OpenMDW-1.1 is a permissive, MIT-like license:
commercial/production use is explicitly permitted, there is no
field-of-use or responsible-use-policy restriction incorporated as a
license term (no medical/healthcare carve-out of any kind), no
attribution requirement beyond retaining the license text and copyright
notices on redistribution, and it explicitly disclaims any restriction on
outputs generated using the model. It adds a defensive patent-and-copyright
litigation termination clause (broader than Apache-2.0's patent-only
clause) and a standard AS-IS warranty disclaimer — neither is a use
restriction. Full reasoning: `docs/architecture/adr/0049-nemotron-second-stt-provider.md`.

**What R2 actually proves, and what it does not, matters as much here as
it did for R0/R1** — see "Concrete answer to the empirical question"
below. The provider implementation, its license disposition, and its
factory wiring are built and merged. Real, empirical STT accuracy numbers
comparing faster-whisper against Nemotron — the thing a full validation
would eventually want — require a real, locally-installed NeMo ASR
checkpoint and real audio, neither available in this session's sandbox
(no GPU, no `nemo_toolkit` install, no model download). This is disclosed
as an explicit, actionable follow-up, exactly like R1's equivalent
Sortformer gap, not silently skipped or assumed passing.

**Recommendation: no urgent need for R3** (MFA alignment evaluation) — see
"Recommendation for R3" below.

## Scope

One branch, `research-r2-nemotron-stt-poc`:

| Area | What shipped |
|---|---|
| Provider | `backend/app/providers/speech_to_text.py` — `NemotronConfig` + `NemotronSpeechProvider`, a second real `SpeechToTextProvider` wrapping NVIDIA NeMo's generic `ASRModel` loader for `nvidia/nemotron-3.5-asr-streaming-0.6b` |
| Wiring | `app.core.ai_providers.get_speech_provider` accepts `VOCADOX_SPEECH_PROVIDER=nemotron`; `Settings.speech_nemotron_model_dir_name` keeps its installed checkpoint in a separate `model_volume_root` subdirectory from faster-whisper's |
| Install | `app/cli/install_models.py`'s new `stt-nemotron` `ModelProfile` (single `.nemo` file, `allow_patterns`-restricted, `requires_token=False`) |
| Dependency | **None new** — Nemotron is a NeMo-native ASR checkpoint; R1's existing `nemo_toolkit[asr]>=2.0,<3.0` extra already covers it. `pyproject.toml`/`uv.lock` unchanged by this PR. |
| Compliance | `compliance/model-inventory.yml` — a real model entry (not a `compliance/exceptions.yml` dev-tool exception, since this ships in the product); `compliance/license-policy.yml`'s `approved` bucket gains `OpenMDW-1.1`, scoped explicitly as model-inventory-only |
| Docs | ADR-0049 (full license research + design decisions), `docs/admin/speech-provider.md`, `docs/admin/model-installation.md` |
| Frontend | `AdminSpeechPage.tsx` — small provider-discoverability note (Card + Badges), reusing existing design-system components, same pattern R1 added to `AdminDiarizationPage.tsx`; no new API field needed since `SpeechProviderStatus` was already provider-agnostic |
| Tests | `backend/tests/test_nemotron_provider.py` (4 new tests: not-installed/installed status, clear error when unloaded, factory selection) + `test_architecture_boundaries.py` updated to include `NemotronSpeechProvider` in the "domain code must not import concrete providers" check |

Out of scope (explicitly, per the R2 task and disclosed in ADR-0049's
"Scope" section): a cross-provider WER/Evaluation Lab comparison endpoint
(`EvaluationRunType.SPEECH_ACCURACY` or similar) — see below. R3 (MFA
alignment evaluation) — untouched. R0/R1's diarization code — untouched.

## Concrete answer to the empirical question

Two separate claims, kept separate, exactly as R0/R1's reports did:

1. **Does `NemotronSpeechProvider` conform to the `SpeechToTextProvider`
   interface and integrate cleanly with the existing factory wiring, with
   no changes needed elsewhere?** **Yes — proven directly.**
   `get_speech_provider()` constructs it correctly for
   `VOCADOX_SPEECH_PROVIDER=nemotron`
   (test: `test_get_speech_provider_selects_nemotron`); its `status()`/
   `transcribe()` not-installed paths raise the same
   `SpeechModelUnavailableError` contract `FasterWhisperSpeechProvider`
   does (3 passing tests); no `pyproject.toml`/`uv.lock` change was needed
   (confirmed by inspecting the existing `[ai]` extra before touching it —
   `nemo_toolkit[asr]` already covers ASR models, not just diarization);
   ruff/mypy/the full backend test suite (495 tests collected — 491 from
   R1 + 4 new — 494 passed, 1 pre-existing skip, same skip as before this
   PR) and the frontend's typecheck/lint/test(64 passed, unchanged)/build
   all pass clean in this session.

2. **Does real Nemotron ASR inference actually produce correct
   transcription output on real audio, and does it actually compare
   meaningfully against faster-whisper's real transcription accuracy?**
   **Not answered — disclosed, not hidden, exactly like R1's equivalent
   gap.** This requires all of:
   - A real, working `nemo_toolkit` install and a real, downloaded `.nemo`
     checkpoint — neither performed in this session (no GPU, no network
     budget for a multi-GB download, matching this project's own
     established "admin explicitly installs real models" pattern).
   - A real cross-provider WER comparison — **deliberately not built in
     this PR** (see "What R2 does and does not wire into the eval
     framework" below), so even with a real install, there is currently no
     ready-made endpoint to run this comparison through; an admin/developer
     would need to adapt `app.analytics.wer.word_error_rate` and
     `run_vocabulary_comparison`'s pattern by hand, or build the
     `SPEECH_ACCURACY` run type ADR-0049 describes as a reasonable future
     step.

   `NemotronSpeechProvider.transcribe()` follows the model card's
   documented usage pattern (`ASRModel.restore_from()` + `.transcribe([path],
   batch_size=1)`) as faithfully as possible but is unverified end-to-end.
   It also has two structural output-richness gaps versus faster-whisper,
   disclosed rather than papered over: no documented word/segment-level
   timestamps or confidence score in the model card's simplest usage
   sample (the whole file is reported as one segment with an honest `0.0`
   confidence placeholder and no `words`), and no audio-duration probing
   (`end_seconds`/`duration_ms` are honestly `0.0`/`None`, not guessed).

Framing (1) as done and (2) as an open, actionable item is the honest
answer here — exactly the discipline R0/R1 established and R2 continues.

## What R2 does and does not wire into the eval framework

The R2 task explicitly asked for a judgment call here: R0's DER/JER eval
framework and R1's Sortformer wiring both reused
`EvaluationRun`/the Evaluation Lab pattern for diarization comparisons.
For STT, this project already has a real, working WER primitive
(`app.analytics.wer.word_error_rate`) and a real Evaluation Lab run type
(`EvaluationRunType.VOCABULARY_COMPARISON`,
`run_vocabulary_comparison` in `app/analytics/service.py`) — but it
exists to compare *the same provider* with/without a resolved custom
vocabulary on one already-reviewed conversation's own audio, not to
compare *two different STT providers* against each other.

**Decision: did not build a new cross-provider comparison endpoint in
this PR.** Reasoning (full account in ADR-0049's "Scope" section):

1. The roadmap explicitly scoped R2 as a "PoC," less integrated than R1's
   own full eval-framework wiring — and even R1's Sortformer wiring never
   built a single combined comparison run (`subject_b` stays reserved;
   comparing providers today means two separate runs, compared by hand).
2. Building a comparison endpoint around a provider whose real
   transcription output shape is itself unverified in this sandbox would
   produce a "PASS" number tied to nothing real — the same
   rubber-stamped-synthetic-fixture risk R0 exists to prevent.
3. Proportionality: adapting `run_vocabulary_comparison`'s machinery to
   compare providers (not configs) is real design work — deciding which
   provider builds `subject_a` vs `subject_b`, what "ground truth" means
   when one provider's output is coarser than the other's — better done
   once a real Nemotron install exists to validate the design against.

**What's left available for a future PR to build on**:
`app.analytics.wer.word_error_rate` is untouched and reusable; the
`EvaluationRunType` enum is a natural place to add a
`SPEECH_ACCURACY` (or similarly named) value following R0/R1's own
precedent exactly.

## Test / CI Summary (local, this session)

- Backend: full suite green — 495 tests collected (491 from R1 + 4 new in
  `test_nemotron_provider.py`), 494 passed, 1 skipped (pre-existing, not
  introduced by this PR), `ruff check .` and `mypy app` both clean across
  now-updated source files.
- No `pyproject.toml`/`uv.lock` change — confirmed unnecessary before
  writing any code by inspecting the `[ai]` extra's existing
  `nemo_toolkit[asr]>=2.0,<3.0` pin (R1); no `uv lock` re-resolution was
  needed or performed.
- `python compliance/check_licenses.py`: **PASS** — 44 direct / 594
  transitive (590 approved, 4 review_required, unchanged from R1) / 6
  containers / **8 models** (was 6; the two new rows are this PR's
  `nvidia/nemotron-3.5-asr-streaming-0.6b` entry, both `approved`), 0
  blocked / 0 unknown across all four categories.
- Frontend: `npm ci` (this session, on the Windows host directly — not
  inside a Linux container against the bind mount, so the project's known
  npm/Docker/Windows gotcha does not apply here), then
  `npm run typecheck` / `npm run lint` / `npm run test` (vitest, 64
  passed, unchanged from R1 — no new suite needed for one static info
  card) / `npm run build` — all clean.
- `frontend/openapi.json` / generated TS client — not regenerated;
  unaffected by this PR (no backend response schema changed —
  `SpeechProviderStatus` was already provider-agnostic on both sides, so
  no OpenAPI drift is expected, matching R1's identical reasoning for its
  own diarization-status field).
- This PR's actual CI run: see the PR for the real, live outcome (this
  report is drafted before CI's own run completes, per this project's
  "poll CI for real, don't guess" discipline — any CI-surfaced finding
  will be recorded via a follow-up commit and an update to this report's
  Findings Register, exactly like R1's real License-compliance-job
  fix-and-repush cycle).

## License Disposition

- **`nvidia/nemotron-3.5-asr-streaming-0.6b` (model weights)**: **OpenMDW-1.1**,
  verified from the license text itself
  (`https://openmdw.ai/license/1-1/`, fetched and read directly,
  2026-09-12) — NOT merely from the model card's prose or a research
  summary. Cross-verified against the Hugging Face model API: `gated:
  false`, `license: "other"` with `license_name: openmdw-1.1`, `sha:
  "ea30d66debe3740a08b573244286791d423d6b3e"` (the exact commit pinned in
  this PR). **No genuine license-policy blocker found**: commercial/
  production use permitted; no field-of-use or responsible-use-policy
  restriction is a legal term of the license itself (the model card's
  separate "Ethical Considerations"/Trustworthy-AI section is guidance,
  not an incorporated license term — this distinction is recorded
  explicitly in ADR-0049, not silently resolved); no medical/healthcare
  carve-out; attribution requirement limited to retaining the license
  text and copyright/origin notices on redistribution (no UI/output
  attribution requirement, unlike Sortformer's CC-BY-4.0); explicit "no
  restrictions on outputs generated using the Model Materials" clause; a
  defensive patent-and-copyright litigation termination clause; standard
  AS-IS warranty disclaimer. Full clause-by-clause account: ADR-0049.
- **`nemo_toolkit` (runtime library, PyPI)**: **Apache-2.0** — already
  verified in R1 (ADR-0048); unchanged by this PR, verified separately
  from the model-weight license per this project's standing rule, no new
  dependency added.
- **Recorded in `compliance/model-inventory.yml`** as a real model entry
  (`bundled_with_product: false`, `downloaded_at_install: true`,
  `approval_status: approved`) — not a `compliance/exceptions.yml`
  dev-tool exception, matching R1's Sortformer precedent (a real,
  admin-installable, shippable production provider, not a dev-only
  test-fixture tool).
- **`compliance/license-policy.yml`**: `OpenMDW-1.1` added to the
  `approved` bucket, explicitly scoped in-line as a model-inventory-only
  entry (not a PyPI/npm dependency license) with the full reasoning
  recorded next to it, so a future reviewer never has to re-derive why it
  was approved.

## Known Limitations / Assumptions (disclosed, not blocking merge of R2 itself)

1. **No real end-to-end Nemotron ASR inference was executed** — no GPU,
   no `nemo_toolkit` install, and no real `.nemo` download in this
   sandbox. `NemotronSpeechProvider.transcribe()` follows the model
   card's documented usage pattern as faithfully as possible but is
   unverified end-to-end. This mirrors exactly how
   `SortformerDiarizationProvider` was first disclosed in R1.
2. **No cross-provider WER comparison exists yet** — see "What R2 does
   and does not wire into the eval framework" above for the full,
   deliberate reasoning. `app.analytics.wer.word_error_rate` remains
   available and unmodified for a future comparison to reuse.
3. **No word/segment-level timestamps or confidence score** from this
   provider's basic `.transcribe()` usage path — the whole file is
   reported as one segment with an honest `0.0` confidence placeholder.
   This is a structural gap versus faster-whisper's richer output, not a
   bug to fix later without further model-card research (e.g. whether a
   richer streaming/timestamped API exists on this checkpoint beyond the
   documented basic sample).
4. **No audio-duration probing** — `end_seconds`/`duration_ms` are
   honestly `0.0`/`None`. Adding real duration detection would need
   either a new dependency or shelling out to `ffprobe`; deliberately out
   of scope for this PoC-scoped provider.
5. **`hotwords`/`initial_prompt` are accepted but have no effect** — no
   documented custom-vocabulary biasing API on this model card's basic
   usage path, unlike faster-whisper's native support for both.

## Findings Register

**License research finding (the centerpiece of this PR, not a defect):**
the R2 task's framing correctly flagged that OpenMDW-1.1 was a genuinely
new, unencountered license category for this project and required real
research rather than an assumption. That research (fetching and reading
the actual license text at `https://openmdw.ai/license/1-1/`, not relying
on the model card's prose or a research-letter summary alone) found the
license to be permissive and MIT-like with no blocking restriction for
commercial medical-documentation use — the one real ambiguity worth
recording (the model card's separate ethical-use/Trustworthy-AI section
vs. the license text's own explicit "no output restrictions" clause) is
disclosed in ADR-0049 rather than silently resolved either way, following
the exact discipline R1's model-card-vs-HF-API gating discrepancy
established.

No CI-fix-and-repush cycle to report yet at the time of this draft (this
PR's CI has not yet completed as this report is written) — unlike R1,
where a real `nemo_toolkit[asr]` dependency addition triggered a genuine
License compliance job failure. R2 added no new dependency, so that
specific risk class does not apply here; if CI still surfaces something
real, it will be fixed with a real follow-up commit and recorded here
before merge, not silently smoothed over.

## Recommendation for R3

**No urgent need for R3** (MFA — Montreal Forced Aligner — alignment
evaluation, per the roadmap's own framing; this report does not re-derive
its exact scope beyond what R0/R1 already established: R3 is explicitly
the lowest-priority stage and should only proceed if R0/R1/R2's own
testing surfaced a real alignment weakness).

Consistent with R0's and R1's own findings: **none of R0, R1, or R2 has
surfaced a real, empirically-observed alignment weakness** — because none
of the three stages has yet been able to run real inference against real
audio in a sandbox with a GPU, a real model download, and a real speech
corpus. This is not evidence that no alignment weakness exists; it is
evidence that the empirical question remains open for the same reason
across all three research stages, and R3 (MFA alignment evaluation) would
face the identical sandbox limitation without first closing R0/R1/R2's
own open items (a real FastMSS-generated fixture batch, a real pyannote
install, a real Sortformer install, and now a real Nemotron install).

**Honest recommendation**: prioritize closing R0/R1/R2's shared empirical
gap (an environment with real network/GPU access to actually install and
run these providers against real audio) over starting R3, since R3's own
alignment question is downstream of the same missing empirical
infrastructure, and the roadmap itself frames R3 as lowest-priority absent
a demonstrated weakness. If the owner has access to such an environment,
the single highest-value next step across all of R0-R2 is the same one
R0's own report named at the outset: run the real providers this session
built/verified-in-shape against real audio once, and let that either
surface a real weakness (which would then make a genuine case for R3) or
close out R0-R2's remaining "Known Limitations" sections for good.
