# AI worker security

## Container vulnerability scan

See `docs/security/ai-worker-vulnerability-triage.md` for the Phase 3.1
individual, per-finding triage of this image's Trivy `HIGH` results (0
CRITICAL, 18 HIGH, all in the base OS layer, all accepted with a
documented reason — not accepted as one aggregate untriaged group, which
is what Phase 3 had time-boxed to).

## Process isolation

`worker-speech`/`worker-diarization` run as separate containers from the
`api` (`backend`) and `frontend` services, sharing only the database and
Valkey queue over the network — a compromised worker process doesn't get
direct filesystem access to the api container or vice versa (standard
Docker Compose network/container isolation).

## Non-root

`backend/worker.Dockerfile` creates and switches to a non-root
`vocadox` user (uid 10001), mirroring `backend/Dockerfile`'s existing
pattern — the worker process never runs as root.

## GPU isolation

Only the worker services request GPU device access
(`deploy.resources.reservations.devices`, commented out by default) — the
`api`/`frontend` containers never do. A vulnerability in the API surface
can't be leveraged to reach GPU-attached hardware through the worker's
device access, since they're different containers entirely.

## No silent network access at runtime

The running worker process never initiates a model download — that only
happens via the explicit, admin-run `app/cli/install_models.py` (see
`docs/security/model-supply-chain.md`). Once models are installed, the
intent is that the worker can run fully offline (see
`docs/operations/offline-model-installation.md` for what was/wasn't
actually verified for this in the current sandbox).

## Logging discipline

Workers log job/run metadata (IDs, provider, model, duration, status,
failure class) — never full transcript text, source audio bytes, or raw
provider-returned payloads. `app/audit/service.py`'s existing rule
(`event_metadata` is small structured non-sensitive context only) is
followed identically for the new `processing.*`/`transcript.*`/
`diarization.*`/`speaker.*` audit events introduced in this phase — see
each event's call site in `app/processing/orchestrator.py`,
`app/transcription/router.py`, `app/diarization/router.py`.

## Subprocess safety (FFmpeg)

`FfmpegMediaNormalizer` invokes `ffmpeg`/`ffprobe` via
`asyncio.create_subprocess_exec` with a fixed argument list — never shell
interpolation, so no argument can be used for shell injection. A
subprocess timeout (`Settings.normalization_subprocess_timeout_seconds`,
default 600s) prevents a malformed/adversarial input file from hanging a
worker indefinitely; controlled temp paths are always cleaned up via
`finally: shutil.rmtree(...)` even on failure.

## Resource limits

An input size cap (`FfmpegMediaNormalizer.max_input_size_bytes`) and
subprocess timeout are enforced for normalization; no cgroup-level
memory/CPU limits are set on the worker containers by VocaDox itself in
Phase 3 — that remains the deploying operator's responsibility (standard
Docker Compose/Kubernetes resource limit configuration), documented here
as a known scope boundary rather than silently assumed handled.
