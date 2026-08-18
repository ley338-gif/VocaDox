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

## Cancellation

Only `QUEUED` jobs can be cleanly cancelled
(`POST /conversations/{id}/processing/{job_id}/cancel`) — a `RUNNING` job
cannot be safely interrupted mid-execution in this phase; the endpoint
returns `409 Conflict` rather than claiming a cancellation that didn't
happen.
