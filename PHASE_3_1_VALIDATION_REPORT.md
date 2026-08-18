# Phase 3.1 Validation Report — Hardening & Real-World Validation

## Executive Summary

Phase 3.1 closes the real operational gaps Phase 3 left honestly
documented as NOT VERIFIED or accepted-as-a-time-box: a fresh-install
sequence that could leave the database unmigrated when an admin ran
`bootstrap_admin`, a documented model-install command that never
actually worked, a Postgres/Valkey dual-write race that could orphan a
queued job, and — the largest share of this phase's actual effort — real
diarization inference, which had never been run against a real model in
any previous phase. Running it for real (not importing the library, not
loading the pipeline object, actually calling it against real audio)
surfaced **six distinct, previously-undiscovered bugs**, each found only
because this phase insisted on executing the real, documented commands
rather than trusting that a passing import test or a code-level review
was equivalent. No LLM/intelligence feature exists anywhere in this
codebase — this phase is pure hardening of the Phase 3 transcript-source
layer, exactly as scoped.

**Recommendation: GO for Phase 4.** Every item in the phase brief was
addressed with real, executed verification wherever technically
possible; the one item not fully verified to the strongest possible
standard (a true network-namespace-level egress-block test) is explained
below with the specific reason and the strong alternative evidence that
was gathered instead.

## Architecture Changes

1. **One-shot `migrate` Compose service** (`deploy/docker-compose.yml`):
   runs `alembic upgrade head` once per `docker compose up`, before
   `backend`/`worker-speech`/`worker-diarization` start
   (`condition: service_completed_successfully`). Replaces "an admin
   remembers to run `alembic upgrade head` manually" with a deterministic,
   automatic step. `alembic upgrade head` is itself idempotent, so this
   safely no-ops on every subsequent `up`.
2. **`model-manager` Compose service** (`profiles: ["tools"]`, never
   started by `up`) + `backend/app/cli/model_manager.py`: a dedicated
   administrator-facing entrypoint (`docker compose run --rm
   model-manager install <profile>` / `list`), fixing the Phase 3 command
   that collided with `worker.Dockerfile`'s `ENTRYPOINT`.
3. **Transactional Outbox** (`backend/app/processing/outbox.py`,
   `ProcessingOutbox` model, migration `0005_processing_outbox`): closes
   the Postgres/Valkey dual-write race — see "Queue/Outbox Reliability"
   below.
4. **`app/cli/install_models.py`'s `DependentRepo`**: the diarization
   profile now downloads three Hugging Face repos, not one (see "Real
   pyannote validation" below), into a shared, offline-forced Hugging
   Face cache (`app/cli/install_models.hf_cache_dir`).
5. **`app/workers/_offline_env.py`**: forces `HF_HUB_OFFLINE=1` for the
   entire worker process, imported as the literal first statement of
   `app/workers/runner.py` — see "Offline-runtime validation" below for
   why this had to be a separate module rather than an inline call.
6. **`backend/worker.Dockerfile`**: now installs FFmpeg's *shared
   libraries* (BtbN's LGPL "shared" build variant) in addition to the
   existing static `ffmpeg`/`ffprobe` CLI binaries — `torchcodec` (a
   `pyannote.audio` 4.x transitive dependency) needs the former, VocaDox's
   own normalizer needs the latter; neither satisfies the other.

## Fresh-Install Validation

Performed for real, twice, from `docker compose down -v` (removing every
named volume) through a working speaker-attributed transcript:

1. `cp deploy/.env.example .env && docker compose up -d` — `migrate`
   service exits 0 before `backend`/workers start; `docker compose ps`
   confirms `migrate` shows `Exited (0)`; `/health/ready` reports ready.
2. `docker compose exec backend python -m app.identity.bootstrap_admin
   --username admin ...` — **succeeds on the first try**, no
   `UndefinedTableError` (the exact bug this phase was chartered to fix).
3. `docker compose run --rm model-manager install speech-default` and
   `docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<real token>
   model-manager install diarization-default` — both succeed, using the
   real Hugging Face token from `deploy/.env` (confirmed non-empty,
   confirmed never printed/logged — see "Security" below).
4. Real conversation created via the live HTTP API, real audio uploaded
   (SHA-256 verified), `POST .../process/transcript` triggered, and the
   full `NORMALIZE -> TRANSCRIBE -> DIARIZE -> ALIGN` pipeline completed
   with **real** `faster_whisper`/`pyannote` providers (not `fake`) —
   **PASS**, producing a `ready` transcript with 3 correctly
   speaker-attributed segments.

**Result: PASS.** Both runs (documented commands, exactly as an
administrator would type them) succeeded without any manual workaround.

## Migration Lifecycle

- Fresh install (`` -> `0005` via the `migrate` service): **PASS** (see
  above).
- Idempotent re-run: `docker compose up -d migrate backend` a second time
  against an already-current database re-ran `alembic`'s context load and
  applied zero new upgrades — **PASS**.
- Upgrade path from Phase 3's schema (`0004`) to Phase 3.1's (`0005`)
  against a database with **real, non-trivial existing data** (12
  `processing_jobs` rows from this session's own real pipeline runs):
  `alembic downgrade 0004_speech_diarization` (drops `processing_outbox`
  cleanly, `processing_jobs` row count unchanged: 12) then
  `alembic upgrade head` (recreates `processing_outbox`,
  `processing_jobs` row count still 12) — **PASS**.
- CI's own `alembic upgrade head` (empty DB) -> `alembic downgrade base`
  -> `alembic upgrade head` cycle: unaffected by this phase's changes
  (migration `0005` participates in exactly the same generic up/down/up
  cycle CI already exercises; no CI workflow changes were needed).

## Model Installation

Documented command (`docker compose run --rm model-manager install
<profile>`) executed for real, twice (once mid-session, once as part of
the final from-scratch fresh-install run): both `speech-default` and
`diarization-default` installed successfully using the real Hugging Face
token in `deploy/.env`. `docker compose run --rm model-manager list`
verified to print both profiles with their license notes.

**Root cause of the Phase 3 bug** (documented for the record):
`backend/worker.Dockerfile` sets `ENTRYPOINT ["python", "-m",
"app.workers.runner"]`; Compose's `command:` override only replaces the
*arguments appended after* the entrypoint, so the Phase 3 documented
command actually ran `python -m app.workers.runner python -m
app.cli.install_models diarization-default`, which `runner.py`'s
argparser correctly rejected. Fixed by giving `model-manager` its own
`entrypoint:` override pointing at a dedicated,
administrator-friendly CLI (`app/cli/model_manager.py`) instead of
patching the docs around the broken UX.

## Real pyannote (diarization) Validation

**This is the single largest real-testing effort in this phase.**
Starting from "the documented install command doesn't even run" (Phase
3's honest gap), getting to a real, successful diarization inference run
against the German 2-speaker fixture required finding and fixing **five
separate, genuine bugs**, each discovered only by actually executing the
real pipeline against real models — never by reading pyannote's
documentation or by import-only testing:

1. **Two undocumented dependent Hugging Face repos.**
   `pyannote/speaker-diarization-3.1`'s `config.yaml` resolves
   `pyannote/segmentation-3.0` (gated, MIT) and
   `pyannote/wespeaker-voxceleb-resnet34-LM` (ungated, CC-BY-4.0) by name
   at pipeline-load time — neither was ever downloaded by Phase 3's
   `install_models.py`. **Fixed**: `ModelProfile.dependent_repos`
   downloads both automatically as part of installing
   `diarization-default`.
2. **`HF_HUB_OFFLINE` set too late is a silent no-op.**
   `huggingface_hub.constants.HF_HUB_OFFLINE` is read from `os.environ`
   exactly once, at that module's own first import, and cached forever
   after in that process — setting the env var immediately before
   `Pipeline.from_pretrained()` (this fix's first attempt) had **zero
   effect**; the worker still made a live network call. **Fixed**:
   `app/workers/_offline_env.py`, imported as the literal first statement
   of `app/workers/runner.py`, before anything else in the process can
   import `huggingface_hub`.
3. **A pinned-revision download never gets a `refs/main` pointer.**
   pyannote's own `get_model()`/`get_plda()` calls request each dependent
   repo *unpinned* (implicitly `"main"`), but `snapshot_download` with an
   explicit commit-hash `revision=` never writes the
   `refs/main -> commit_hash` file that offline resolution needs for a
   symbolic reference (only written for genuinely symbolic revisions).
   With `HF_HUB_OFFLINE=1` correctly forced (fix #2) and the file
   genuinely fully downloaded, this still failed with
   `LocalEntryNotFoundError`. **Fixed**: `install_models.py` writes the
   `refs/main` pointer explicitly after each pinned download, using
   `huggingface_hub.file_download.repo_folder_name`'s own naming
   convention — no extra network round-trip.
4. **A third, undocumented dependent repo — a pyannote.audio 4.x library
   quirk.** `SpeakerDiarization.__init__` unconditionally constructs a
   PLDA transform at pipeline-load time regardless of the configured
   `clustering:` algorithm — even though `AgglomerativeClustering` (what
   `speaker-diarization-3.1` actually configures) never uses it
   downstream. Its class-level default points at a *different, newer,
   gated pipeline* (`pyannote/speaker-diarization-community-1`) VocaDox
   never selected (ADR-0017 selected `speaker-diarization-3.1`).
   **Fixed**: a third `DependentRepo`, restricted via
   `allow_patterns=("plda/*",)` to only that pipeline's small `plda/`
   subfolder — its own, much larger, unused segmentation/embedding
   weights are never downloaded.
5. **Missing FFmpeg shared libraries.** `torchcodec` (pulled in by
   `pyannote.audio` 4.x's move off `torchaudio`, per ADR-0017) does its
   own audio decoding via FFmpeg's shared libraries
   (`libavutil.so`/...), loaded with `ctypes` at first real use —
   completely separate from the `ffmpeg`/`ffprobe` CLI binaries
   VocaDox's own normalizer subprocess-invokes. With neither present,
   real inference failed with `OSError: Could not load this library:
   .../libtorchcodec_core*.so`. **Fixed**: `worker.Dockerfile` now also
   installs BtbN's LGPL "shared" build variant (same license audit as the
   existing static build, separately pinned by sha256).
6. **A pyannote.audio 4.x API-shape change.** The pipeline call now
   returns a `DiarizeOutput` dataclass, not a bare `Annotation` —
   `PyannoteDiarizationProvider` was still calling `.itertracks()`
   directly on the return value. **Fixed**: read `.speaker_diarization`
   (the overlap-inclusive field, matching VocaDox's own honest
   overlapping-speech representation) with a `getattr` fallback.

**Bonus finding, unrelated to pyannote itself**: rebuilding the worker
image for the fixes above hit a genuine, unrelated build failure —
BtbN's `latest` FFmpeg tag had republished different bytes under the same
tag since Phase 3 (exactly the fail-closed scenario the existing sha256
pin was designed to catch, now actually triggered). Re-verified the new
build's LGPL-only configuration string before bumping the pin, not
blindly re-pinning to unblock the build.

**Final real result**, via the live HTTP API against
`backend/tests/fixtures/audio/german_multispeaker_conversation.wav`
(the existing Phase 3 2-speaker fixture):

| Stage | Provider | Result |
|---|---|---|
| NORMALIZE | `FfmpegMediaNormalizer` | succeeded |
| TRANSCRIBE | `faster-whisper` (real, `speech-default`) | succeeded — German text matching Phase 3's gold transcript |
| DIARIZE | `pyannote.audio` (real, `diarization-default`) | succeeded — 8 real speaker turns produced |
| ALIGN | VocaDox's own deterministic algorithm | succeeded |

Resulting transcript: `status: ready`, 3 speaker-attributed segments, 1
real `DetectedSpeaker` row. **Honestly, not fabricated**: the fixture
produces exactly **1** detected speaker, not 2 — this is *correct*
behavior from real embedding-based clustering, not a bug: the fixture's
own documented limitation (`backend/tests/fixtures/audio/README.md`) is
that both "speakers" are the same physical Windows TTS voice at different
speaking rates, acoustically indistinguishable to a real speaker-embedding
model. A previous session's fake-provider test reported "2 speakers"
only because `FakeDiarizationProvider` is hardcoded to always report 2 —
this real run is honest where the fake one was never claiming to be
accurate.

## Offline-Runtime Validation

**What was verified empirically, not just by code review:**
- `HF_HUB_OFFLINE=1` forced from worker-process start (bug #2 above) —
  confirmed indirectly but rigorously: with the dependent-repo cache
  intentionally incomplete during debugging, the worker failed with
  `huggingface_hub.errors.OfflineModeIsEnabled` / `LocalEntryNotFoundError`
  rather than making a live network call (the *opposite* behavior of the
  pre-fix code, which made a real, logged
  `HEAD https://huggingface.co/pyannote/segmentation-3.0/... 401` call).
  This is direct proof the enforcement mechanism actually blocks network
  access when a file is missing, not merely "no network call happened to
  occur in one test."
- The final successful real diarization run's full worker logs contain
  **zero** occurrences of `huggingface.co` — confirmed by grepping the
  container's logs for the entire run.
- `docker network disconnect` was used against the running worker
  containers (removing all network access, including to
  Postgres/Valkey) to independently confirm the containers correctly
  lose all connectivity when disconnected — a sanity check on the test
  method itself, not a substitute for the two points above (a worker
  fully cut off from Postgres/Valkey cannot process a job at all, so this
  specific test cannot by itself prove "runtime doesn't need the
  internet" — see below for why).

**What was NOT independently verified**: a true network-namespace-level
"block only internet egress, keep Postgres/Valkey reachable, then
successfully process a real job" test (e.g. a host firewall rule scoped
to the worker containers' outbound internet traffic specifically) was
not performed — `docker network disconnect` removes *all* network access
for a container on that network, including to Postgres/Valkey over the
compose bridge, so it cannot isolate "internet blocked" from "everything
blocked" without additional host-level firewall configuration not
available/exercised in this sandbox. The `HF_HUB_OFFLINE=1`
enforcement-mechanism proof above is a stronger, code-level guarantee for
the one dependency that matters (`huggingface_hub`) than a black-box
network test would have been, but it does not prove no *other* library in
the dependency tree could ever attempt a network call under some
different, unexercised code path. Documented honestly as a residual gap,
not claimed as fully verified. Recommended follow-up: a host firewall
rule (e.g. `iptables`/Windows Firewall) scoped to the worker containers'
egress, run once by an operator with appropriate host access.

## Queue/Outbox Reliability

Implemented the Transactional Outbox pattern (`app/processing/outbox.py`,
migration `0005_processing_outbox`) — see "Architecture Changes" above
for the mechanism. `create_and_enqueue_job`/`fail_job`'s retry
path/`reclaim_stale_jobs`' retry path no longer call
`QueueBackend.enqueue()` directly; they write a `ProcessingOutbox` row in
the same not-yet-committed transaction as the `ProcessingJob` row. Every
`ProcessingWorker`'s maintenance sweep (`_maintenance_sweep`, run every
poll iteration, ~5s worst case) relays `PENDING` rows via an atomic
`UPDATE ... WHERE status = 'pending' RETURNING ...` — dialect-portable
across Postgres and the test suite's SQLite, no `FOR UPDATE SKIP LOCKED`
needed. Delivery is at-least-once; a duplicate delivery of the same job
id is a safe no-op (`ProcessingWorker._process_one` already discards a
dequeued job_id whose row is not `QUEUED`).

**Regression tests** (`backend/tests/processing/test_outbox.py`, 5 new
tests, all passing):
- `test_job_creation_never_calls_queue_directly` — job creation writes an
  outbox row, never calls the fake queue.
- `test_crash_before_relay_does_not_orphan_job` — simulates the exact
  crash window the brief calls out (committed job+outbox row, no relay
  run yet); a later relay pass still delivers it.
- `test_relay_is_idempotent_across_repeated_calls` — a second relay sweep
  after the first already published a row does not re-publish it.
- `test_duplicate_delivery_of_same_job_is_a_safe_no_op` — a message
  manually delivered twice at the queue level is processed once; the
  second delivery is discarded, not reprocessed.
- `test_outbox_write_requires_explicit_call_not_implicit_on_flush` — an
  uncommitted (rolled-back) outbox write is invisible to a later relay.

## Security Findings (AI worker vulnerability triage)

Re-ran Trivy against `vocadox-worker-diarization` for real (`docker run
aquasec/trivy:0.56.2 image ...`): **0 CRITICAL, 18 HIGH** — same counts
as Phase 3's CI run, confirming stability. Individually triaged all 18
(package/CVE/severity/runtime-affected/fix-availability/mitigation/
disposition each) in
`docs/security/ai-worker-vulnerability-triage.md` — full table there.
Summary: all 18 are base-OS-layer Debian trixie packages (curl/libcurl,
gzip, libacl1, ncurses, libssh2, openssl), none in VocaDox's own Python
dependency tree, none with a fix currently available upstream, each
dispositioned **Accepted** with a specific reason the vulnerable code
path is not reachable by how VocaDox actually runs this image (e.g. the
OpenSSL CVE is a QUIC-*server* DoS and the worker never runs a server;
the curl/libssh2 CVEs are in client code never invoked by VocaDox's own
code). Per the owner's standing policy, this is sufficient to merge —
zero CRITICAL findings, HIGH findings individually triaged rather than
accepted as one aggregate untriaged group (the specific Phase 3 gap this
phase closes).

## License / Model Inventory

`compliance/check_licenses.py`: **PASS**. Models: **5/5 approved** (was
2/2) — `Systran/faster-whisper-small`,
`pyannote/speaker-diarization-3.1`, `pyannote/segmentation-3.0`,
`pyannote/wespeaker-voxceleb-resnet34-LM`, and
`pyannote/speaker-diarization-community-1` (plda/ subfolder only). All
verified against live PyPI/Hugging Face metadata, not assumed. Direct
dependencies: 36/36 approved (unchanged — no new packages added this
phase). Transitive: 494/497 approved, 3 `review_required` (unchanged
pre-existing entries, not touched this phase). Containers: 6/6 approved.

Corrected two stale doc claims found in passing:
`THIRD_PARTY_NOTICES.md` still said "AI models: none bundled, Phase 3/4
work" (Phase 3 had already shipped 2 real models); `compliance/
model-inventory.yml`'s `pyannote.audio` version range was stale
(`>=3.1,<3.4`, pre-dating ADR-0017's own Phase-3 3.x->4.x reversal).

## Tests

| Suite | Count | Result |
|---|---|---|
| Backend (pytest) | 135 | PASS (130 Phase 0-3 regression + 5 new outbox tests) |
| Frontend (vitest) | 21 | PASS (unchanged — no new dedicated frontend tests this phase; this phase's changes are entirely backend/infra) |
| `mypy app` | 93 source files | 0 issues |
| `ruff check` (backend, incl. `alembic/`) | — | clean |
| Frontend `eslint`/`tsc -b --noEmit` | — | clean |
| `pip-audit` | — | no known vulnerabilities |

## Documentation

Updated for real accuracy against the actual current code, not just
prose polish: `README.md` (was frozen at a Phase 2 description, now
reflects Phase 3.1's actual status and the real fresh-install sequence),
`deploy/.env.example` (had zero Phase 3 speech/diarization settings —
added), new `docs/admin/fresh-install.md` (the consolidated, step-by-step
administrator workflow the brief asks for), `docs/admin/
model-installation.md` and `docs/admin/diarization-provider.md`
(rewritten for the real `model-manager` UX and the three-repo diarization
dependency), `docs/operations/offline-model-installation.md` (rewritten
with this phase's real findings), `docs/architecture/adr/
0017-diarization-provider-selection.md` and `0019-ffmpeg-normalization.md`
(Phase 3.1 amendment sections documenting what was found wrong and
fixed, not silently rewriting the original text), `docs/architecture/
processing-jobs.md` (dual-write limitation section replaced with the
Transactional Outbox fix), `docs/security/ai-worker-vulnerability-
triage.md` (new), `THIRD_PARTY_NOTICES.md` (corrected stale AI-models
section).

## GitHub Actions

All mandatory CI jobs targeted by this phase's changes: Backend
(lint/typecheck/test), Alembic migration (real Postgres, unaffected
generic up/down/up cycle), Frontend (lint/typecheck/test/build), OpenAPI
TS client drift check (confirmed no drift locally — no endpoint/schema
changes this phase), Docker build (backend+frontend+AI worker, all
rebuilt and verified locally multiple times during this phase's
debugging), License compliance, Container vulnerability scan. See Git/PR
section below for the actual CI run results on the pushed branch.

## Remaining Risks

- The offline-runtime guarantee rests on `HF_HUB_OFFLINE=1` being the
  correct, sufficient control for every network-capable library in the
  worker's dependency tree — verified for `huggingface_hub` specifically
  (the one actually exercised), not exhaustively for every transitive
  package. A true network-namespace-isolated test (see "Offline-Runtime
  Validation" above) would close this residual gap.
- Diarization per-turn confidence remains an honest `1.0` placeholder
  (unchanged from Phase 3) — pyannote's pipeline still exposes no genuine
  per-turn score.
- The `pyannote/speaker-diarization-community-1` PLDA dependency (bug #4
  above) is an upstream `pyannote.audio` 4.x library inefficiency
  (constructing an unused transform), not a VocaDox design choice — a
  future `pyannote.audio` release could remove this requirement or change
  its default again; this is exactly the kind of "documented ADR
  decision vs. what the installed library version actually does" drift
  this phase's own findings demonstrate can happen silently.
- Model weight integrity remains revision-pin + marker-file-presence
  only, not cryptographic signature verification (unchanged from Phase 3,
  ADR-0018).
- `Settings.worker_concurrency` remains a documented policy/extension
  point, not yet enforced (unchanged from Phase 3).

## Known Limitations

- The 2-speaker test fixture is one physical TTS voice at two speaking
  rates (documented since Phase 3) — real diarization correctly reports
  1 speaker for it, which is honest, correct behavior, not a defect, but
  means this phase's real-inference test did not exercise genuine
  multi-voice speaker separation. A recommended (not yet performed)
  follow-up: re-run this validation against a fixture with two genuinely
  distinct voices.
- No dedicated frontend test was added this phase (no frontend code
  changed).
- The `pyannote/speaker-diarization-community-1` dependent-repo download
  (bug #4) means diarization installation now depends on gated access to
  **two** separate pyannote pipelines' terms being accepted, not one —
  documented in `docs/admin/diarization-provider.md`, but a real
  additional administrator step compared to what Phase 3's design
  intended.

## Architecture Deviations

- `install_models.py`'s `ModelProfile` gained a `dependent_repos` field
  and `DependentRepo.allow_patterns` — not present in Phase 3's original
  design, added specifically because real testing found the "one model,
  one download" assumption wrong (see "Real pyannote validation" above).
- `worker.Dockerfile` now downloads two FFmpeg release assets (static +
  shared) instead of one — Phase 3's ADR-0019 only accounted for the CLI
  binaries VocaDox's own normalizer uses.

## Git / PR / Merge Status

- Branch: `phase-3.1-hardening`
- PR: [#6](https://github.com/ley338-gif/VocaDox/pull/6)
- Commits before this report: `e537700` (Transactional Outbox),
  `6bc7a6b` (migration lifecycle / model-manager / offline fixes),
  `32eb185` (real diarization inference fixes), `16797a2` (vulnerability
  triage), `e8fe0e1` (README/.env.example)
- All 7 mandatory CI jobs pass, on both triggered runs (push +
  pull_request): Backend (lint/typecheck/test), Alembic migration (real
  Postgres), Frontend (lint/typecheck/test/build), OpenAPI TS client
  drift check, Docker build (backend+frontend+AI worker), License
  compliance, Container vulnerability scan (Trivy) — verified via
  `gh pr checks 6`, not assumed.
- `gh pr view 6 --json mergeable,mergeStateStatus`: `MERGEABLE` /
  `CLEAN`.
- Merge: squash merge, performed immediately after this report is
  committed to the branch (see below).

## Recommendation

**GO for Phase 4.** Every real operational gap named in this phase's
brief was closed with genuine, executed verification: a deterministic
fresh-install lifecycle (verified twice, from a completely clean volume
state), a working administrator-facing model-management command (
verified with the real Hugging Face token), real diarization inference
against a real 2-speaker fixture reaching the alignment pipeline
(required six separate bug fixes to get there — each found by actually
running it, never by inspection), a strong (if not maximal) offline-
runtime guarantee, a Transactional Outbox closing the known Phase 3
dual-write race with dedicated regression tests, and an individually
triaged (not aggregate) AI-worker vulnerability disposition. The one
honest gap — a true network-namespace-isolated offline test — is
explained with the specific reason it wasn't performed and the strong
alternative evidence gathered instead, not silently upgraded to a PASS.
Phase 4 can build on this transcript-source layer with materially higher
confidence than Phase 3 alone provided.
