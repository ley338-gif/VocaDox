# Processing jobs

## ProcessingJob vs. ProcessingRun

Two different concerns, kept in separate tables (`app/processing/models.py`):

- **`ProcessingJob`** — orchestration: what work is queued/running/done,
  retries, worker ownership, lease. Ephemeral in spirit (though rows are
  kept for history).
- **`ProcessingRun`** — provenance: what a *successful* (or attempted)
  execution actually produced — provider, model, model_revision,
  configuration_snapshot, timestamps, raw provider output.

A job may fail before ever producing a run (e.g. before invoking a
provider at all); a run always corresponds to one job's execution.

## Job types and queues

`NORMALIZE`, `TRANSCRIBE`, `DIARIZE`, `ALIGN` — see
`app/processing/queues.py` for which worker role consumes which queue,
and `docs/architecture/adr/0020-worker-topology.md` for why the split is
`worker-speech` (NORMALIZE, TRANSCRIBE) / `worker-diarization` (DIARIZE,
ALIGN).

## Chaining

`app/processing/orchestrator.py` ties the stages together:
`NORMALIZE` success -> enqueue `TRANSCRIBE` (+`DIARIZE` if requested) ->
whichever of `TRANSCRIBE`/`DIARIZE` finishes **second** enqueues `ALIGN`
(`maybe_trigger_align`). No polling/waiting job is ever needed — each
stage's completion handler checks whether the other prerequisite already
exists.

## States and retry

`QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED`. Failure is
classified (`app/processing/retry.py`):

| FailureClass | Retryable? | Example |
|---|---|---|
| TRANSIENT | Yes | worker hiccup, network blip |
| RESOURCE | Yes | transient VRAM pressure |
| PERMANENT | No | corrupt/unsupported audio |
| INPUT_INVALID | No | bad input data |
| MODEL_UNAVAILABLE | No | model not installed — needs an admin action |

A retryable failure requeues the *same* job row (incrementing `attempt`)
up to `max_attempts` (default 3); beyond that, or for a non-retryable
class, the job is terminally `FAILED` and a user/admin must explicitly
retry via `POST /conversations/{id}/processing/retry` (which creates a
**new** job).

## Idempotency

`get_active_job`/`get_or_create_job` ensure at most one non-terminal job
of a given type exists per source media at a time — repeated `POST
.../process/transcript` calls don't create unlimited duplicate work (see
`app/processing/service.py`).

## Worker crash recovery

Every `RUNNING` job carries `lease_expires_at`. `reclaim_stale_jobs` (run
at the top of every worker poll loop) finds jobs whose lease expired
without the owning worker renewing it and requeues them (or fails them
terminally if `max_attempts` is exhausted) — a crashed worker never
leaves a job stuck `RUNNING` forever. Tested in
`tests/processing/test_pipeline_api.py::test_worker_lease_expiry_reclaims_stale_running_job`.

## Fixed in Phase 3.1: Transactional Outbox (was: dual-write between Valkey and Postgres)

Phase 3's `create_and_enqueue_job` did `session.add(job)` + `flush()` then
`queue.enqueue(...)` directly — these were not one atomic operation.
Found by real fresh-install testing (not hypothesized): if the *caller*
of `create_and_enqueue_job` (e.g. `trigger_post_normalize`, which creates
TRANSCRIBE and DIARIZE in the same success-handler call) raised **after**
the enqueue but **before** the surrounding session committed, the DB row
was rolled back while the Valkey message was already sent — an orphaned
message referencing a job_id that no longer existed.

Phase 3.1 replaced the direct `queue.enqueue()` call with a
**Transactional Outbox** (`app/processing/outbox.py`,
`app.processing.models.ProcessingOutbox`, migration `0005`):
`create_and_enqueue_job`/`fail_job`'s retry path/`reclaim_stale_jobs`'s
retry path now write a `ProcessingOutbox` row in the SAME
not-yet-committed transaction as the `ProcessingJob` row itself — either
both are durable or neither is, by construction, not by careful call
ordering. A separate relay (`relay_pending_outbox`, run by every worker's
`_maintenance_sweep` on every poll iteration, ~5s worst case) atomically
claims PENDING rows and publishes them to Valkey; delivery is
at-least-once, and a duplicate delivery of the same job id is always a
safe no-op (`ProcessingWorker._process_one` already discards a dequeued
job_id whose row is not `QUEUED`). A crash between the DB commit and the
relay running no longer orphans anything — the outbox row is still
PENDING and gets picked up by the next sweep, from any worker process,
not just the one that created it.

Regression coverage: `tests/processing/test_outbox.py` (5 tests) —
job creation never calls the queue directly, crash-before-relay does not
orphan the job, relay is idempotent across repeated sweeps, a duplicate
queue delivery is a safe no-op, and an uncommitted outbox write is
invisible to a later relay.

## Cancellation

Only `QUEUED` jobs can be cleanly cancelled
(`POST /conversations/{id}/processing/{job_id}/cancel`) — a `RUNNING` job
cannot be safely interrupted mid-execution in this phase; the endpoint
returns `409 Conflict` rather than claiming a cancellation that didn't
happen.
