# 0018 — Model installation strategy: downloaded-at-install-time, not bundled

## Status
Accepted

## Context
Speech/diarization model weights are hundreds of MB to low GB each. The
brief explicitly prefers "downloaded during explicit admin step" over
"bundled into images" to avoid multi-GB blobs in application images, and
requires: known source, pinned revision, documented/accepted license,
checksum/revision validation, persistent model volume, recoverable
failure, no silent unreviewed auto-update.

## Decision
Models are **never** baked into `backend/Dockerfile`, `backend/worker.Dockerfile`,
or the git repository. Instead:

1. A persistent named volume, `vocadox_models_data`, mounted at
   `/app/data/models` in both worker containers (`worker-speech`,
   `worker-diarization`) — deliberately separate from
   `vocadox_backend_data` (conversation media), so operators can back up,
   inspect, or wipe models independently of conversation data.
2. An explicit CLI, `python -m app.cli.install_models <profile>`
   (`app/cli/install_models.py`), run by an admin inside the worker
   container (or a one-off `docker compose run worker-speech python -m
   app.cli.install_models speech-default`). It:
   - downloads a **pinned revision** (commit hash) from Hugging Face via
     `huggingface_hub.snapshot_download`, never a floating tag;
   - is **idempotent**: if the target directory already contains the
     expected marker file, it prints "already installed" and does not
     re-download (satisfies "no silent re-download every restart");
   - for a gated model (the diarization pipeline, ADR-0017), requires an
     explicit `--token`/`VOCADOX_HUGGINGFACE_TOKEN` — never invented,
     never defaulted, never logged;
   - verifies the download landed (marker file present) and exits
     non-zero with a clear message on any failure, rather than leaving a
     half-downloaded directory that a provider would later fail on
     confusingly.
3. `Settings.speech_provider`/`diarization_provider` default to `"fake"` —
   a fresh `docker compose up` never attempts to load a model that was
   never installed. An operator explicitly opts in by setting
   `VOCADOX_SPEECH_PROVIDER=faster_whisper` (and the equivalent for
   diarization) after running the install step.
4. `SpeechProviderStatus`/`DiarizationProviderStatus.installed` is a real
   filesystem check (`model.bin`/pipeline files present), never a
   hardcoded `True` — the admin provider-status endpoints (ADR-0023) show
   "Not installed" honestly when it hasn't been done yet.

## Consequences
- Fresh `docker compose up` stays fast and small for the common case
  (fake providers only) — matches "don't make CPU-only deployment
  impossible to inspect/start."
- Real-model validation (this phase's sandbox testing) always ran the
  install step explicitly and recorded the exact command/output in
  PHASE_3_VALIDATION_REPORT.md, rather than asserting "it would work."
- No signed-verification of downloaded weights exists yet (only
  revision-pin + marker-file-presence integrity) — documented as a Known
  Limitation; full checksum/signature verification of the entire
  downloaded tree is deferred to a future phase's Model Management work
  (spec explicitly scopes the full admin Model Management UI to Phase 7).
