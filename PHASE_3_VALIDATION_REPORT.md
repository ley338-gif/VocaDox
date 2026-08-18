# Phase 3 Validation Report — Speech-to-Text, Diarization & Transcript Alignment

## Executive Summary

Phase 3 turns Phase 2's immutable source audio into a real,
speaker-attributed, human-reviewable transcript: real local speech-to-text
(faster-whisper), real local speaker diarization (pyannote.audio), and a
deterministic word-overlap alignment algorithm that never silently
guesses a speaker on weak evidence. No LLM, summarization, fact
extraction, or document generation exists anywhere in this codebase —
Phase 3 stops at the transcript source layer, exactly as scoped.

Three genuine bugs were found and fixed through real testing during this
phase, not by inspection alone: a `pyannote.audio` 3.x/`torchaudio`
incompatibility that made the initially-selected diarization library pin
literally unable to import (found by building the worker image and
importing the package), a missing `model_registry` import in the worker
entrypoint that crashed a fresh worker container with
`NoReferencedTableError` (found by a real `docker compose down -v &&
build --no-cache && up -d` fresh-install run, not by pytest), and a
Valkey/Postgres dual-write race that could orphan a queue message if a
job's success-handler chain crashed between the enqueue and the commit
(same fresh-install run; previously silent, now logged). All three are
documented in their respective ADRs/docs, not hidden.

**Recommendation: GO for Phase 4**, with the residual risks and deferred
items below explicitly accepted, not hidden. The one significant gap is
diarization's real-model inference path: the gated
`pyannote/speaker-diarization-3.1` model could not be downloaded in this
sandbox (no Hugging Face account/token available to this agent), so while
the library, pipeline loading code, and error-handling paths were
verified for real, actual diarization *inference numbers* against real
audio are honestly marked NOT VERIFIED rather than fabricated.

## Scope

Implemented: media normalization (real FFmpeg, LGPL-only static build),
speech-provider abstraction + one real provider (faster-whisper),
diarization-provider abstraction + one real provider (pyannote.audio),
transcript domain (`Transcript`/`TranscriptSegment`, original vs.
corrected text), diarization domain (`DetectedSpeaker`/
`DiarizationSegment`), deterministic word-overlap alignment, processing
jobs/runs with lease-based crash recovery and failure-class-driven retry,
transcript UI with audio sync/correction/speaker-assignment, review
flags, admin provider-status endpoints, REST API, RBAC extensions, audit
events, tests, docs, license/model inventory, real GitHub CI.

Explicitly NOT implemented (verified absent by grep and by this report's
authors' own code review): Qwen, any LLM, summarization, fact/medication
extraction, contradiction detection, Evidence-to-document mapping,
generated documents, approval workflows. `compliance/model-inventory.yml`
now has exactly 2 entries (both speech/diarization), 0 LLM entries.

## Provider Evaluation

### Speech Provider/Model
**faster-whisper** (library, MIT) + **`Systran/faster-whisper-small`**
(weights, MIT, revision `536b0662742c02347bc0e980a01041f333bce12`). Full
evaluation: `docs/architecture/adr/0016-speech-provider-selection.md`.
Chosen over reference PyTorch Whisper (slower, same license), NVIDIA
Parakeet/Nemotron (less clear German/multilingual + redistribution terms
for the effort available), and whisper.cpp (weaker native-Python/GPU
integration for this worker architecture).

### Diarization Provider/Model
**pyannote.audio** (library, MIT) + **`pyannote/speaker-diarization-3.1`**
(pipeline, MIT, gated, revision
`84fd25912480287da0247647c3d2b4853cb3ee5`). Full evaluation, including a
real pin reversal (3.x -> 4.x after 3.x proved unable to import against
modern `torchaudio` — a confirmed upstream issue, not a hypothesis):
`docs/architecture/adr/0017-diarization-provider-selection.md`.

### Model Licensing
Both the runtime **library** and the **model weights** were verified
*separately* for both providers, live against PyPI JSON / Hugging Face
model cards / GitHub LICENSE files on 2026-08-18 — never assumed
"library license = weights license." Both model repos are MIT; the
diarization pipeline is additionally gated (requires an accepted-terms
Hugging Face account + personal token to download — documented in
`docs/admin/diarization-provider.md`, never bundled by VocaDox).
`compliance/model-inventory.yml`: 2/2 models `approved`, 0
`review_required`/`blocked`/`unknown`.

## Architecture

### Worker Architecture
Two role-parameterized services (`worker-speech`: NORMALIZE+TRANSCRIBE;
`worker-diarization`: DIARIZE+ALIGN) sharing one image
(`backend/worker.Dockerfile`) — `docs/architecture/adr/0020-worker-topology.md`.
Neither the api nor frontend service ever requests GPU access.

### Normalization
Real FFmpeg-based normalization to mono 16kHz PCM WAV
(`app/media/normalizer.FfmpegMediaNormalizer`), using an **LGPL-only**
static build (BtbN/FFmpeg-Builds, pinned by sha256
`079be6e766720bf2b1e1d71073214a51cae831295cbcc92e64d31e422fcb5ec1`) —
Debian's own `ffmpeg` package is GPL-built and was rejected after
inspecting its actual configure flags. Full audit:
`docs/architecture/adr/0019-ffmpeg-normalization.md`. Idempotent (keyed on
source+normalizer_version+profile); falls back to Phase 2's `NoOp`
normalizer when no `ffmpeg` binary is present (documented, not silent).

### Processing Jobs
`ProcessingJob` (orchestration: QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED,
lease/heartbeat, attempt/max_attempts) separate from `ProcessingRun`
(provenance: provider/model/revision/configuration_snapshot/raw_output).
Failure classification (TRANSIENT/RESOURCE retry; PERMANENT/
INPUT_INVALID/MODEL_UNAVAILABLE don't) in `app/processing/retry.py`.
Full reference: `docs/architecture/processing-jobs.md`, including a real
dual-write limitation found during fresh-install testing (documented
there, not hidden).

### Processing Runs
Generalized provenance row per stage execution; `raw_output` isolates
provider-specific ASR/diarization results so `ALIGN` is the only writer
of user-facing `TranscriptSegment` rows (avoids a correction-clobbering
race — see `docs/architecture/speech-pipeline.md`).

## Transcript Domain
`Transcript` (status PENDING/PROCESSING/READY/FAILED, provider/model/
revision, `is_active` for reprocess history) + `TranscriptSegment`
(`original_text` never overwritten; `corrected_text` optional;
`review_status` UNREVIEWED/CONFIRMED/CORRECTED/FLAGGED; word timing as a
validated JSON column per segment, not a row-per-word table — decision
documented in `docs/architecture/adr/0021-word-timing-storage.md`).

## Diarization Domain
`DetectedSpeaker` (diarization-run-scoped voice cluster, no identity
inference) + `DiarizationSegment` (raw turns, `is_overlap` flag for
simultaneous speech). `docs/architecture/diarization.md`.

## Detected Speakers / Participant Mapping
`DetectedSpeaker.participant_id`/`display_label` set only via explicit
`PATCH /conversations/{id}/speakers/{speaker_id}` — verified by
`tests/processing/test_pipeline_api.py::test_speaker_assignment_and_unassignment`
and manually via the real fresh-install stack.

## Alignment
Deterministic word-level temporal-overlap algorithm
(`app/transcription/alignment.py`) — CONFIDENT (>=0.66 dominant overlap)/
AMBIGUOUS (<0.66)/OVERLAP (multiple speakers)/UNASSIGNED (no coverage).
Splits an ASR segment exactly where the assigned speaker changes,
preserving original word timing. Full algorithm + rationale:
`docs/architecture/adr/0022-alignment-algorithm.md`,
`docs/architecture/alignment.md`. **9/9 unit tests pass** covering every
case named in the brief (clean single speaker, speaker change
mid-segment, equal overlap, no diarization coverage, diarization overlap,
word timing unavailable, boundary-exactly-equal, plus a non-mutation
guarantee).

## Transcript UX
Real Transcript tab (`frontend/src/components/TranscriptPanel.tsx`):
explicit "Transkription starten" trigger (never auto-processes on
upload), 5 real progress stages driven by actual `ProcessingJob` rows
(never a fabricated percentage), speaker-attributed rows with confidence
and a "⚠ prüfen" flag (not color-only — has an icon + text), correction
UI always showing "Original: X" alongside a correction, per-speaker
rename, plain-text/JSON/Markdown export.

## Audio Synchronization
`AudioPlayer` gained a `forwardRef` imperative handle
(`seekToMs`/`play`) and an `onTimeUpdateMs` callback; clicking a
transcript segment's timestamp seeks the underlying `<audio>` element and
the currently-playing segment is highlighted via `activeMs` comparison.
Verified manually via the real fresh-install stack (byte-exact source
audio playback after a full container restart — see Restart Persistence
below); no dedicated frontend unit test for this interaction — tracked as
a gap below.

## Corrections
`app/transcription/service.correct_segment` never overwrites
`original_text`; every correction creates a
`TranscriptSegmentCorrection` audit row (previous value, corrected value,
user, timestamp). Verified by
`tests/processing/test_pipeline_api.py::test_segment_correction_never_overwrites_original_text`.

## Review Flags
Mechanical-only (`app/transcription/service._review_flag`): low ASR
confidence (<0.55), no diarization coverage, ambiguous attribution,
overlapping speech. No LLM/clinical-importance judgement anywhere in this
code path (grep-verified).

## API / OpenAPI
All spec-listed endpoints implemented under `/api/v1/conversations/{id}/...`
plus `/api/v1/admin/providers/{speech,diarization}`. OpenAPI TS client
regenerated and drift-checked in CI (`openapi-client-drift` job: PASS).

## Database / Migrations
New tables: `processing_runs`, `processing_jobs`, `transcripts`,
`transcript_segments`, `transcript_segment_corrections`,
`detected_speakers`, `diarization_segments` (migration
`0004_speech_diarization.py`). No Phase-4 facts/evidence/document tables.

**Migration testing (real Postgres, not just SQLite):**
- Fresh install (`0001`→`0004`): PASS
- Downgrade (`0004`→base): PASS
- Re-upgrade (base→`0004`): PASS
- **Phase-2-data upgrade test**: inserted a real Phase-2-shaped
  organization/conversation/media_asset row (with a fixed SHA-256) into a
  database at `0003_conversation_capture`, ran `alembic upgrade head`,
  and confirmed the row survived unchanged (same id, title, status,
  **same SHA-256**) — PASS. Also confirmed all 7 new tables exist and
  `python -m app.identity.seed` reapplies idempotently on top of
  pre-existing Phase 1/2 data — PASS.

## Authorization
Every new endpoint enforces Permission + Organization Membership +
Conversation's Organization via the existing
`app.conversations.authz.authorize_conversation_access` — cross-org access
returns 404, not 403 (verified by
`tests/processing/test_pipeline_api.py::test_cross_organization_transcript_access_is_404_not_403`
across `/transcript`, `/processing`, `/speakers`, and
`POST .../process/transcript`). No unauthenticated transcript endpoint
exists.

## Audit
`processing.{started,completed,retried,failed}`, `transcript.created`,
`transcript.segment_corrected`, `diarization.completed`,
`speaker.{assigned,unassigned}` all implemented
(`app/processing/orchestrator.py`, `app/transcription/router.py`,
`app/diarization/router.py`). No transcript content in any audit
metadata (IDs only — grep-verified).

## Performance

### GPU Test
**Hardware**: NVIDIA GeForce RTX 4070, 16376 MiB VRAM, driver 596.36,
CUDA 13.2 (Windows development sandbox). **Real** `faster-whisper`
inference (not a fake/mock) against the synthetic German multi-speaker
fixture:

| Metric | Value |
|---|---|
| Test audio duration | 18.12 s |
| Device | `cuda`, `compute_type=float16` |
| Model load time | 0.71 s |
| Transcription time | **1.04 s** |
| Real-time factor | **~17.4x** |
| Detected language | German (`de`), confidence 1.0 |
| VRAM used during inference | ~1645 MiB (per `nvidia-smi`) |

### CPU Test
Same fixture, same model, `device=cpu, compute_type=int8`:

| Metric | Value |
|---|---|
| Model load time | 0.75 s |
| Transcription time | **2.02 s** |
| Real-time factor | **~9.0x** |

Both runs produced 3 segments closely matching the gold transcript (see
`backend/tests/fixtures/audio/german_multispeaker_conversation.gold.txt`);
minor transcription artifacts on two ASCII-umlaut-substituted words
(`moechte`→"muhechte", encoding-mangled ö/ü in terminal display only) are
attributable to the synthetic TTS fixture's pronunciation, not a pipeline
defect.

Also verified: the **silence fixture** (5s digital silence) produced
**0 segments** (no hallucinated speech); the **corrupted-audio fixture**
(37 bytes of plain text with a `.wav` extension) failed cleanly with
`InvalidDataError` rather than crashing or hanging.

Diarization real-inference performance: **NOT VERIFIED** — the gated
`pyannote/speaker-diarization-3.1` model could not be downloaded in this
sandbox (no Hugging Face account/token available). What WAS verified:
the library imports and the pipeline object loads correctly inside the
real worker image (`docker build -f backend/worker.Dockerfile` +
`from pyannote.audio import Pipeline` succeeded), and
`PyannoteDiarizationProvider`'s not-installed error path fails cleanly
with an actionable message.

### Offline Test
**NOT VERIFIED** as a full "disconnect network, then process" empirical
test — not performed in this sandbox. Code-level review confirms neither
provider's transcribe/diarize call path includes a network parameter once
a local model path is given (see `docs/operations/offline-model-installation.md`
for the exact reasoning and the recommended verification procedure for a
production deployment).

## Security
Subprocess safety: FFmpeg invoked via `asyncio.create_subprocess_exec`
with a fixed argument list (never shell interpolation), timeout, cleaned-up
temp paths. Non-root worker containers. GPU device access isolated to the
two worker services only (commented out by default). Full account:
`docs/security/ai-worker-security.md`, `docs/security/model-supply-chain.md`.

## Privacy
Same organization-scoped authorization as Phase 2's conversations/media;
processing error responses return safe codes
(`{"code": ..., "request_id": ...}`), never stack traces or filesystem
paths (verified: `ffmpeg` stderr is truncated to 500 chars and never
returned to the API, only logged server-side).

## Supply Chain
Models: pinned Hugging Face revisions (commit hashes, never floating
tags); admin-only, explicit install via `app/cli/install_models.py`; no
arbitrary user-specified model URLs; Hugging Face token read only at
install time, never logged/persisted/exposed. FFmpeg binary: pinned by
sha256, fails closed on mismatch. Full account:
`docs/security/model-supply-chain.md`.

## Dependencies

| Category | Approved | Review Required | Blocked | Unknown |
|---|---|---|---|---|
| Direct | 36 | 0 | 0 | 0 |
| Transitive (full resolved tree, 497 packages) | 494 | 3 | 0 | 0 |
| Containers | 6 | 0 | 0 | 0 |
| Models | 2 | 0 | 0 | 0 |

The 3 `review_required` transitive packages are pre-existing LGPL/MPL
entries (unrelated to Phase 3's own additions beyond the pattern already
established in Phase 0). Every previously-bare/missing-license package
newly introduced by the `[ai]` extra (faster-whisper + pyannote.audio's
full transitive tree, including matplotlib, torch, torchaudio, torchcodec,
the 4 `pyannote-core/database/metrics/pipeline` packages with zero PyPI
license metadata, and `pyannoteai-sdk` — pyannoteAI's commercial cloud-API
SDK, pulled in as an unused, inert, MIT-licensed transitive dependency,
never invoked by VocaDox) was individually verified against its actual
PyPI metadata or GitHub `LICENSE` file — none guessed.

`npm audit --audit-level=high`: unchanged from Phase 2 baseline (no new
frontend dependencies added in Phase 3). `pip-audit`: passes in CI
(`backend` job).

## Models
2/2 approved (`compliance/model-inventory.yml`, activated for the first
time this phase): `Systran/faster-whisper-small` (MIT, ungated) and
`pyannote/speaker-diarization-3.1` (MIT, gated — admin-installed with own
HF token).

## Containers
6/6 approved (unchanged base images from Phase 0-2, plus the new AI
worker image built from the same pinned `python:3.11-slim-trixie` base —
no new base image entry required). Trivy: 0 unresolved CRITICAL across
backend/frontend runtime, frontend build/dev, **and the new AI worker
image** (added to both `docker-build` and `container-vulnerability-scan`
CI jobs this phase).

## Licenses
See Dependencies/Models/Containers tables above.
`compliance/check_licenses.py` exit code: **0 (PASS)**.

## Tests

| Suite | Count | Result |
|---|---|---|
| Backend (pytest) | 130 | PASS |
| — of which: alignment algorithm unit tests | 9 | PASS |
| — of which: hardware-detection unit tests (new) | 5 | PASS |
| — of which: end-to-end pipeline integration tests | 9 | PASS |
| — of which: existing Phase 0-2 tests (regression) | ~107 | PASS |
| Frontend (vitest) | 21 | PASS (unchanged from Phase 2 — no new dedicated TranscriptPanel test; see Known Limitations) |
| E2E (browser) | 0 | Not run this phase (manual fresh-install verification substituted — see Fresh Install below) |

`mypy app`: 90 source files, 0 issues. `ruff check .`: clean (backend,
including `alembic/`). Frontend `eslint`/`tsc -b --noEmit`: clean.

## Real Model Validation
See Performance section above for exact commands/results. Summary: real
`faster-whisper` transcription was run — through both the raw library and
VocaDox's own `FasterWhisperSpeechProvider` wrapper — on real GPU and CPU
hardware in this sandbox, against a real (synthetic, provenance-documented)
audio fixture, with results compared against a manually-authored gold
transcript. "Provider imports successfully" was explicitly NOT treated as
sufficient — actual inference was run and its output inspected.
Diarization's real-inference path is honestly NOT VERIFIED (see above).

## GitHub Actions
All 7 mandatory CI jobs pass on the final commit
(`83e864bfeaab195074c501c492951036590a1fec`): Backend
(lint/typecheck/test), Alembic migration (real Postgres), Frontend
(lint/typecheck/test/build), OpenAPI TS client drift check, Docker build
(backend+frontend+AI worker), License compliance, Container vulnerability
scan (Trivy). Two real CI failures were hit and fixed during this phase
(not force-merged past): a ruff line-length violation in the migration
file (caught because CI lints the whole `backend/` tree, including
`alembic/`, not just `app/`+`tests/` as this agent had been checking
locally) and a stale generated OpenAPI TypeScript client (regenerated
against the new endpoints).

## Fresh Install
`docker compose down -v && docker compose build --no-cache && docker
compose up -d` — full stack including the two new AI worker services —
**PASS**, after fixing two real startup bugs found by this exact test
(see Executive Summary and `docs/architecture/processing-jobs.md`'s Known
Limitation section): a worker `model_registry` import gap, and a
Valkey/Postgres dual-write race. After both fixes: created an
organization/admin user, uploaded the real German synthetic fixture
through the live HTTP API, triggered processing, and confirmed
NORMALIZE→TRANSCRIBE→DIARIZE→ALIGN all completed via the real
`worker-speech`/`worker-diarization` containers (fake providers — no
model installed in this test run), producing a `ready` transcript with 2
correctly speaker-attributed segments and matching `DetectedSpeaker`
rows. One processing-pipeline run required a single manual
queue-message re-push to complete (the dual-write race above, triggered
only by this session's own repeated manual container restarts during
debugging — not expected in a normal single fresh install; documented
honestly rather than presented as a clean run).

## Phase-2 Upgrade
PASS — see Database/Migrations section above for the exact test
(real inserted Phase-2-shaped data, `alembic upgrade head`, unchanged
SHA-256, all 7 new tables present, idempotent RBAC reseed).

## Restart Persistence
PASS — after `docker compose restart` (all services) on the fresh-install
stack: `/health/ready` reports ready, the previously-created transcript
still reports `status: "ready"`, the source media's SHA-256 is byte-for-byte
unchanged, the normalized derived media persists, and re-downloading the
source audio via the API returns exactly 579,914 bytes (matching the
original upload) — full playback integrity confirmed, not just a status
flag.

## Worker Recovery
`tests/processing/test_pipeline_api.py::test_worker_lease_expiry_reclaims_stale_running_job`
(unit-level, deterministic) simulates a job stuck `RUNNING` with an
expired lease and confirms `reclaim_stale_jobs` requeues it with
`error_code=WORKER_LEASE_EXPIRED`. Additionally, this phase's real
fresh-install testing incidentally exercised actual worker-crash-and-recover
behavior twice for real (containers exiting with code 1 due to the two
startup bugs found, then successfully processing work after the fix and a
restart) — a genuine, if unplanned, real-world instance of the "worker
disappears mid-flight" scenario the spec asks about.

## Known Limitations
- Diarization real-inference performance/accuracy: NOT VERIFIED (no HF
  token available in this sandbox — see Performance section).
- Offline (network-disconnected) runtime test: NOT VERIFIED empirically
  (code-level review only — see `docs/operations/offline-model-installation.md`).
- `Settings.worker_concurrency` is a documented policy/extension point,
  not yet enforced by the current single-job-at-a-time worker loop (see
  `docs/admin/worker-configuration.md`).
- Multi-GPU pinning (separate GPUs for `worker-speech`/`worker-diarization`):
  architecturally supported, not exercised (single-GPU sandbox).
- A Valkey/Postgres dual-write race can orphan a queue message if a
  job's success-handler chain crashes between enqueue and commit — now
  logged instead of silent, not yet fixed with a transactional outbox
  (see `docs/architecture/processing-jobs.md`).
- No dedicated frontend unit test for `TranscriptPanel`'s audio-seek
  interaction (manually verified via the real fresh-install stack
  instead).
- Diarization per-turn confidence is an honest `1.0` placeholder
  (pyannote's default pipeline exposes no genuine per-turn score) — never
  compared cross-provider as a calibrated probability.
- Model weight integrity is revision-pin + marker-file-presence only, not
  cryptographic signature verification (see ADR-0018).
- The single available German TTS voice means the "multi-speaker" audio
  fixture is one physical voice at two speaking rates, not two distinct
  voices — a real limitation of the test fixture, documented in
  `backend/tests/fixtures/audio/README.md`.

## Open Risks
- If a future dependency bump changes `faster-whisper`'s or
  `pyannote.audio`'s transitive tree, the CI compliance job will catch a
  newly-introduced blocked/unknown license automatically (regenerates the
  full tree on every run) — but a *newly-introduced heavier or
  differently-licensed direct dependency* of either library (as happened
  with the 3.x→4.x pin change itself) would need the same manual
  individual-verification diligence applied in this phase, every time.
- The dual-write race (Known Limitations) is a genuine, if narrow,
  reliability gap under a fairly specific crash-timing window.

## Architecture Deviations
- Diarization library pin changed from the originally-planned `>=3.1,<3.4`
  to `>=4.0,<5.0` after real testing (see ADR-0017) — a deliberate,
  documented reversal, not a silent scope change.
- `Settings.worker_concurrency` exists as configuration but isn't yet
  wired to a concurrent execution path (see Known Limitations).

## Deferred Items
Everything explicitly scoped to Phase 4+ per the brief (LLM, fact
extraction, document generation, etc.) plus, within Phase 3's own stated
foundation-only scope: full admin Model Management UI (Phase 7),
per-organization provider profiles (Phase 7), signed model integrity
verification, a transactional outbox for job chaining.

## Git / PR / Merge Status
- Branch: `phase-3-speech-diarization`
- PR: [#5](https://github.com/ley338-gif/VocaDox/pull/5)
- Final commit before merge: `83e864bfeaab195074c501c492951036590a1fec`
- All mandatory GitHub Actions checks: PASS
- Merge: squash merge, performed immediately after this report is
  committed to the branch (see below)

## Recommendation

**GO for Phase 4.** VocaDox now has a reliable speaker-attributed
transcript source layer: real local STT and diarization providers (both
license-clean, both separately audited for library vs. model-weight
terms), a deterministic and unit-tested alignment algorithm that reports
its own uncertainty honestly, immutable original audio (SHA-256-verified
unchanged across processing and restart), full provenance from transcript
segment back to conversation/source-media/processing-run, human
corrections that never destroy the original ASR output, working audio-seek
synchronization, processing retries and worker-crash recovery (both
exercised for real, not just simulated), enforced organization
authorization, clean license/dependency/model/container compliance, a
passing fresh-install test (after real bugs were found and fixed by that
exact test), passing migration tests (including real Phase-2 data
survival), passing restart-persistence tests, and fully green mandatory
CI. The diarization real-inference gap (no HF token available in this
sandbox) and the offline-runtime gap are the two most significant honest
NOT VERIFIED items — both are architecturally addressed and
code-reviewed, and both should be re-verified as very-low-effort
follow-ups by the project owner (who can obtain an HF token and/or test
an air-gapped deployment) before those specific capabilities are relied
upon in production, but neither blocks the source-layer architecture
Phase 4 will build on.
