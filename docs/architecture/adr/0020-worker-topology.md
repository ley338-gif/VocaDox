# 0020 — Worker topology: two role-parameterized services, one image

## Status
Accepted

## Context
Phase 3 is the first phase that genuinely requires long-running
background processing — transcription and diarization must never run
inside an HTTP request. The brief allows either `api`/`worker-speech`/
`worker-diarization` or a single combined worker, "choose based on clean
evolution toward multiple GPU workers later."

## Decision
One worker **image** (`backend/worker.Dockerfile`), one worker
**process implementation** (`app/workers/processing_worker.ProcessingWorker`
+ `app/workers/runner.py`), started as **two Compose services**:
`worker-speech` (`--role speech`) and `worker-diarization` (`--role
diarization`). Each role only dequeues from its own job-type queues
(`app/processing/queues.py`):

- `worker-speech`: `NORMALIZE`, `TRANSCRIBE`
- `worker-diarization`: `DIARIZE`, `ALIGN` (ALIGN is CPU-only/cheap and
  only ever runs once a DIARIZATION run exists when diarization was
  requested, so it rides along with that worker rather than needing a
  third service)

`ProcessingJob.job_type` still has all four values as first-class,
independently-tracked rows (spec requirement) — the two-service split is
purely about which *process* picks up which *queue*, not a change to the
job/provenance model.

## Why not a single combined worker
A single worker process handling all four job types would be simpler
today, but would force NORMALIZE/TRANSCRIBE (CPU-or-GPU, Whisper-sized
VRAM) and DIARIZE (separate GPU-sized VRAM, different pretrained
pipeline) onto the same process/GPU allocation. Splitting now means:
- `deploy/docker-compose.yml`'s `deploy.resources.reservations.devices`
  block can be uncommented independently per service — e.g. speech on
  GPU 0, diarization on GPU 1, or diarization staying CPU-only while
  speech gets the GPU — without any code change.
- `Settings.worker_concurrency` (default 1, "safe default... one
  GPU-heavy job per worker") is meaningful per-role rather than needing to
  arbitrate between two different model types loaded into the same
  process's memory.

## Why not Kubernetes-style scheduling
Explicitly out of scope per the brief ("don't build Kubernetes-style
scheduling"). Job dispatch is a simple two-queue poll
(`app/processing/service.dequeue_next`), not a scheduler; worker-crash
recovery is a lease/heartbeat expiry sweep
(`app/processing/service.reclaim_stale_jobs`), not distributed consensus.

## Consequences
- `deploy/docker-compose.yml` builds `worker-speech`/`worker-diarization`
  from the same `backend/worker.Dockerfile` context — one image, two
  `command:` overrides.
- The `api` (`backend` service) and `frontend` service never request GPU
  device access — only the two worker services do (commented-out by
  default; see docs/operations/gpu-runtime.md) — satisfying "GPU
  isolation."
- `ProcessingWorker`'s dependencies (queue, storage, providers,
  sessionmaker) are all constructor-injectable, which is what let
  `tests/processing/` run the full pipeline against two in-process
  `ProcessingWorker` instances (mirroring the real speech/diarization
  split) with zero real Valkey/Postgres/GPU.
