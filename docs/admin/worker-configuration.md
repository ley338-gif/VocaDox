# Worker configuration

## Topology

Two worker services (see `docs/architecture/adr/0020-worker-topology.md`):

- **`worker-speech`** — consumes `NORMALIZE` and `TRANSCRIBE` jobs.
- **`worker-diarization`** — consumes `DIARIZE` and `ALIGN` jobs.

Both run from the same image (`backend/worker.Dockerfile`), started with
a different `--role` argument. Neither the `backend` (api) nor `frontend`
service ever needs (or gets) GPU access — only these two do.

## Concurrency

`Settings.worker_concurrency` (env `VOCADOX_WORKER_CONCURRENCY`, default
`1`) is the intended cap on simultaneous GPU-heavy jobs per worker
process. **Current implementation note:** the Phase 3 worker loop
processes one job at a time per process by construction (a single
sequential `run_forever` loop) — the setting exists as the documented
policy and extension point for a future concurrent-execution
implementation (e.g. multiple asyncio tasks bounded by a semaphore), not
yet wired to a concurrent executor. Scaling out today means running
additional worker *containers*, not raising this number.

## Scaling

Add more `worker-speech`/`worker-diarization` replicas in
`deploy/docker-compose.yml` (or your orchestrator) to increase throughput
— jobs are claimed via `dequeue_next` against the shared Valkey queues, so
multiple worker processes safely compete for work without double-processing
(each job is claimed by exactly one worker via its `QUEUED -> RUNNING`
transition).

## Job leases and crash recovery

Every `RUNNING` job carries a lease (`Settings.job_lease_seconds`, default
300s). If a worker crashes mid-job, the lease expires and any worker's
periodic `reclaim_stale_jobs` sweep (top of every poll loop) requeues it
— see `docs/operations/processing-troubleshooting.md` for what this looks
like in practice.

## Queue fairness

`Settings.max_active_processing_jobs_per_conversation` (default `3`)
caps how many concurrent jobs one conversation can have queued/running —
a user repeatedly clicking "Transkription starten" can't create unbounded
work.

## Logs

Workers log `job_id`, `job_type`, `failure_class`, `conversation_id`,
`processing_run_id`, provider/model/duration/status — **never** full
transcript text, source audio, or raw provider payloads (see
`docs/security/ai-worker-security.md`).
