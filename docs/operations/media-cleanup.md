# Operations: media cleanup

## Temp upload directory

`Settings.upload_temp_dir` (default `./data/tmp-uploads`) receives
spooled uploads before they're validated/hashed and atomically moved into
permanent storage. The application itself deletes temp files on:
- Validation failure (empty file, oversize, unrecognized format).
- Ingestion failure after the temp file was spooled but before the move
  into permanent storage succeeded.

**What is not yet automated**: if the backend process is killed (OOM,
crash, forced container restart) mid-upload, the partially-written temp
file is not cleaned up by any code path — the OS does not auto-clear a
bind-mounted `upload_temp_dir` the way it might a true `/tmp` on some
platforms.

**Interim mitigation** (until a scheduled sweep ships): a periodic cron/
systemd-timer job on the host (or an init container) that removes files
under `upload_temp_dir` older than, say, `upload_timeout_seconds × 2` is
safe — any file that old is guaranteed to belong to an upload that either
completed (and was already moved/deleted) or failed outright. Example:

```sh
find /path/to/data/tmp-uploads -type f -mmin +20 -delete
```

## Abandoned recording-upload sessions

`RecordingUpload` rows with `status = in_progress` past their
`expires_at` represent an abandoned finalize attempt. Phase 2 does not run
a background job to mark these `EXPIRED` or clean up any associated
partial data — the finalize endpoint itself is idempotent per
`idempotency_key`
([ADR-0012](../architecture/adr/0012-chunked-upload-decision.md)), so an
abandoned session simply never gets a `result_media_id` and can be
identified later with:

```sql
SELECT id, conversation_id, started_at, expires_at
FROM recording_uploads
WHERE status = 'in_progress' AND expires_at < now();
```

Deleting or expiring these rows is safe (no media was ever finalized
against them) — a scheduled cleanup for this is a reasonable follow-up
item, not implemented in Phase 2.

## Deleted-conversation media

`DELETE /conversations/{id}` destroys physical media synchronously in the
same request — there is no deferred/background cleanup step to monitor
for that path (see
[ADR-0015](../architecture/adr/0015-retention-and-deletion-semantics.md)).
