# Processing troubleshooting

## "Transcription failed — Model unavailable"

The speech or diarization model isn't installed on the worker that
picked up the job. Check `GET /api/v1/admin/providers/speech` /
`.../diarization` for `installed: false`, then follow
`docs/admin/model-installation.md`. This failure is classified
`MODEL_UNAVAILABLE` and is never auto-retried — install the model, then
use the Retry button/`POST .../processing/retry`.

## A job seems stuck in "Preparing audio" / "Transcribing" / etc.

1. Check `GET /conversations/{id}/processing` for the job's `status`,
   `attempt`, `error_code`.
2. If `status: running` for an unusually long time, the owning worker may
   have crashed without releasing its lease — it will be automatically
   reclaimed and requeued within `Settings.job_lease_seconds` (default
   300s) by any worker's next poll-loop sweep
   (`reclaim_stale_jobs`). Check worker container logs
   (`docker compose logs worker-speech worker-diarization`) for a crash.
3. If it stays `queued` indefinitely, confirm the relevant worker
   container is actually running (`docker compose ps`) and can reach
   Valkey/Postgres.

## Repeated `INPUT_INVALID` / `PERMANENT` failures

These are never auto-retried — check the conversation's source audio.
Common causes: a corrupted upload, an unsupported/unrecognized codec that
even FFmpeg couldn't decode, or an empty/near-empty file. The safe error
code and (non-sensitive) message are in
`ProcessingJob.error_code`/`error_message_safe`; the underlying detail
(e.g. ffmpeg's actual stderr) is in the worker's server-side logs only,
never returned to the client.

## Diarization returns an unexpected number of speakers

- Provide `min_speakers`/`max_speakers` hints on the next processing
  request if you know the expected count.
- Background noise, music, or heavy cross-talk can cause over/under-
  counting — this is a real limitation of the underlying model, not a
  VocaDox bug; see `docs/architecture/diarization.md`'s honesty notes on
  overlap/confidence.

## "Too many active processing jobs" (429)

`Settings.max_active_processing_jobs_per_conversation` (default 3) was
hit — wait for existing jobs to finish, or cancel a queued one
(`POST /conversations/{id}/processing/{job_id}/cancel` — only `QUEUED`
jobs can be cancelled).

## Checking without touching the database directly

Everything above is visible via the documented API endpoints
(`GET .../processing`, `GET /api/v1/admin/providers/speech|diarization`)
— avoid querying `processing_jobs`/`processing_runs` directly except for
deep debugging, since the API surface is what stays stable across schema
changes.
