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

## Known limitation: dual-write between Valkey and Postgres

`create_and_enqueue_job` does `session.add(job)` + `flush()` then
`queue.enqueue(...)` — these are not one atomic operation. Found by real
fresh-install testing (not hypothesized): if the *caller* of
`create_and_enqueue_job` (e.g. `trigger_post_normalize`, which creates
TRANSCRIBE and DIARIZE in the same success-handler call) raises **after**
the enqueue but **before** the surrounding session commits, the DB row is
rolled back while the Valkey message was already sent — an orphaned
message referencing a job_id that no longer exists. A worker dequeuing it
finds `load_job(...) is None` and discards it — logged as a warning
(`"discarded a dequeued job_id with no matching QUEUED row"`) rather than
silently swallowed, so an admin can tell this happened, but the
downstream stage genuinely does not get (re-)triggered automatically.
Recovery today is manual (an admin/operator re-enqueueing the affected
stage, or the user re-triggering "reprocess"). A fully transactional
outbox pattern (only enqueue after commit, via a durable local record) is
the correct long-term fix and is not implemented in Phase 3 — documented
here as a real, encountered limitation rather than swept under the rug.

## Cancellation

Only `QUEUED` jobs can be cleanly cancelled
(`POST /conversations/{id}/processing/{job_id}/cancel`) — a `RUNNING` job
cannot be safely interrupted mid-execution in this phase; the endpoint
returns `409 Conflict` rather than claiming a cancellation that didn't
happen.
