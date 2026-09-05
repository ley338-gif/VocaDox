# Disaster Recovery: Backup, Restore, and Retention Cleanup

This is the concrete, operator-facing runbook for Phase 11's real backup/
restore mechanism (`app.operations.backup_service`) and the Retention
Cleanup Worker (`app.operations.retention_service`). Everything below was
run for real against Docker infrastructure while writing this document —
see `PHASE_11_VALIDATION_REPORT.md`'s Backup/Restore/Retention Cleanup
sections for the full transcript. This is not generic disaster-recovery
advice; it describes exactly what this codebase does and does not do.

## What is backed up, and what is not

A backup (`POST /admin/operations/backups`, or `docker compose run --rm
backup create`) covers:

- **The entire PostgreSQL database** — a `pg_dump --format=custom` of
  every table: Documents, Transcripts, Conversations, Templates,
  Processing Profiles, RetentionPolicy rows, users/roles/permissions,
  audit log, service accounts, webhooks — everything in `Base.metadata`,
  with no per-table allowlist to keep in sync.
- **Retained media** — a tar archive of `media_storage_root` (the
  `vocadox_backend_data` volume's `media/` subdirectory): source audio,
  normalized audio, attachments.

A backup does **not** cover:

- The `vocadox_models_data` volume (installed AI models) — deliberately
  out of scope, see `app/operations/__init__.py`'s module docstring and
  ADR-0018 ("don't mix model files with Conversation media/backups").
  Models are reinstalled via `docker compose run --rm model-manager
  install <profile>`, not restored from a backup.
- Valkey's contents — sessions and rate-limit counters, which are
  intentionally ephemeral and safe to lose (every session simply expires
  and users log in again; no durable data lives there).
- The backup artifacts' own storage. `backup_root` (the
  `vocadox_backups_data` volume, or `VOCADOX_BACKUP_ROOT` in a bare-metal
  deploy) is **not itself backed up by anything in this codebase.** If
  it lives on the same host/volume as the primary database, a
  whole-host failure destroys both the data and its backups
  simultaneously — see "Off-host backup storage" below.

## Creating a backup

```sh
# Via the admin API (requires backup:trigger permission):
curl -X POST https://<host>/api/v1/admin/operations/backups \
  -H "X-CSRF-Token: <token>" --cookie <session-cookie-jar>

# Via the CLI (no HTTP auth needed — run this on/near the host):
docker compose run --rm backup create
```

Each backup writes `<backup_root>/<backup_id>/database.dump` (pg_dump
custom format) and `<backup_root>/<backup_id>/media.tar`, and records a
`BackupRecord` row (status, byte counts, timestamps) — visible at `GET
/admin/operations/backups` or `docker compose run --rm backup list`, and
in the Admin Portal's **Operations** page. A `backup.created` audit event
and (if webhooks are configured) a `backup.created` webhook delivery are
also emitted.

**Observed real timing** (synthetic single-conversation dataset, this
phase's own validation run): a few hundred milliseconds end-to-end for a
near-empty database. This scales primarily with `pg_dump`'s dump time
(proportional to total row count/size) and the media tar's total byte
size — for a production-sized database, benchmark your own real dataset
rather than assuming this number.

## Restoring a backup — CLI-only, by design

**Restore is never available over HTTP, on any admin page, on purpose.**
See `app/operations/backup_service.py`'s module docstring for the full
reasoning: `pg_restore --clean` genuinely drops and recreates every
object the dump describes, an in-process request handler cannot safely
run that against its own live connection pool, and a destructive
whole-database operation should never be one accidental button click
away. The only way to restore is:

```sh
docker compose run --rm backup restore <backup_id_or_directory>
```

This is **destructive**: it drops and recreates the entire target
database's schema+data from the dump (`pg_restore --clean --if-exists`),
and it deletes and replaces the entire target `media_storage_root`
directory with the tar's contents. Never run this against a database you
intend to keep any current data in.

### Real restore-into-fresh-infrastructure test (this phase)

Performed for real, not simulated, as part of writing this document:

1. Seeded a real organization/conversation/media asset (real bytes,
   real sha256)/transcript into a live Postgres 17.6 container.
2. `docker compose run --rm backup create` — produced a real backup.
3. Simulated total infrastructure loss: stopped and removed the
   `postgres`/`valkey` containers and deleted the
   `vocadox_postgres_data`/`vocadox_backend_data`/`vocadox_valkey_data`
   volumes — **keeping only `vocadox_backups_data`**, exactly as a real
   off-host backup would survive a host failure that destroys everything
   else.
4. Brought up a brand-new, completely unmigrated Postgres container (no
   `alembic upgrade head` run against it at all).
5. `docker compose run --rm backup restore <backup_id>` — succeeded.
6. Verified: the conversation row was present; the restored media file
   on disk matched the original sha256 exactly (byte-for-byte); the
   transcript segment text matched exactly; and a subsequent normal
   `migrate` run against the restored database found it already at
   `alembic` head (correctly a no-op) — confirming `pg_dump`'s
   full-schema dump means **a restored target needs no separate schema
   migration step at all.**

This is the concrete evidence behind this runbook's RTO/RPO claims below,
not an assumption.

### Restoring into a Kubernetes / non-Compose deployment

The CLI itself has no Docker Compose dependency — `python -m
app.cli.backup restore <backup_dir>` runs anywhere the application image
runs, given `VOCADOX_DATABASE_URL` pointing at the target database and
the same `pg_restore` binary version story documented below. In a
Kubernetes deployment, run it as a one-off `Job`/`kubectl exec` using the
same container image, with the backup artifact directory mounted (or
copied in) from wherever `backup_root` actually lives.

## RPO / RTO — realistic, given what is actually implemented

- **RPO (Recovery Point Objective) = time since the last successful
  backup.** There is no continuous replication or WAL-shipping in this
  codebase — only point-in-time `pg_dump` snapshots, triggered manually
  or on whatever external schedule an operator wires up (cron, a
  Kubernetes CronJob calling `docker compose run --rm backup create`).
  **This phase ships no automatic backup schedule** — an operator must
  configure one. Until one exists, RPO is "however long since the last
  time someone clicked Create Backup," which is not an acceptable
  production posture on its own — see "Operator setup checklist" below.
- **RTO (Recovery Time Objective) = time to bring up fresh infrastructure
  + restore time.** Restore time itself is dominated by `pg_restore`'s
  data-loading time (proportional to the dump's size) and the media
  tar's extraction time — both real, measurable, and roughly linear in
  data volume; benchmark against your own production data size. Fresh
  infrastructure stand-up time (pulling images, starting Postgres, etc.)
  is typically the dominant cost for a small dataset, as observed in
  this phase's own test above (image pulls/builds took far longer than
  the actual restore).

## Operator setup checklist (this codebase does none of this for you)

1. **Schedule regular backups.** `docker compose run --rm backup create`
   on a cron/CronJob, at whatever interval your acceptable RPO requires.
2. **Off-host backup storage.** Mount `backup_root` /
   `vocadox_backups_data` on separate physical/cloud storage from
   `vocadox_postgres_data` — ideally off the primary host entirely (a
   separate NFS/object-storage-backed volume, or a periodic `rsync`/
   `aws s3 sync` of the backup directory to remote storage). This
   codebase does not do this automatically; see
   `docs/architecture/future-considerations.md`'s Phase 11 section for
   why this was deliberately deferred rather than built with a
   fabricated cloud-storage target.
3. **Backup retention/rotation.** Nothing here prunes old backups — set
   up your own rotation (e.g. `find <backup_root> -maxdepth 1 -mtime
   +30 -exec rm -rf {} \;`) sized to your actual retention requirements
   and storage budget.
4. **Test your restore, not just your backup.** A backup nobody has ever
   restored is not a verified backup — periodically restore into a
   scratch environment (exactly as this document's own test did) and
   confirm the data is what you expect.
5. **Postgres client/server version matching.** The backend image's
   `postgresql-client` package version tracks whatever the base Debian
   image (`python:3.11-slim-trixie`) ships — currently 17.x. If a future
   base-image bump changes that, and the deployed Postgres server major
   version is not bumped to match, `pg_dump`/`pg_restore` can fail with
   the same class of "unrecognized configuration parameter" error this
   phase found and fixed (see `deploy/docker-compose.yml`'s comment on
   the `postgres` service and `compliance/container-inventory.yml`).
   Keep them in sync.

## Retention Cleanup

`app.operations.retention_service.run_retention_cleanup` is the real
enforcement of the `RetentionPolicy` model (existing since Phase 2, with
admin CRUD since Phase 7, with zero enforcement until this phase).

**Safe by default: every call site defaults to a dry run.**
`RetentionCleanupRunRequest.dry_run` (the admin API) and `app.cli.
retention_cleanup run` (the CLI) both default to `dry_run=True` — nothing
is ever deleted unless an admin explicitly checks "Actually delete" in
the Admin Portal, explicitly passes `{"dry_run": false}` to the API, or
explicitly passes `--execute` to the CLI.

```sh
docker compose run --rm retention-cleanup run            # dry run — deletes nothing
docker compose run --rm retention-cleanup run --execute   # REAL, IRREVERSIBLE deletion
```

Real physical deletion, never a soft-delete flag alone: media bytes are
removed from storage (`StorageProvider.delete`) before the `MediaAsset`
row is tombstoned (`deleted_at` set, row kept for provenance — never the
bytes), and transcript deletion is a genuine SQL `DELETE` (with
`TranscriptSegment`/`TranscriptSegmentCorrection` cascading at the
database FK level) — never a blanked-in-place row. Every individual
deletion is recorded as its own `RetentionCleanupItem` row (policy,
threshold, action, byte count — never the deleted content itself)
*before* the physical action happens, so the audit trail exists even if
the run subsequently fails partway through.

### Real test performed in this phase

Both the `pytest` suite (`backend/tests/operations/
test_retention_service.py`, 9 tests against a real SQLite database and
real bytes on a real temp-directory filesystem — see that file for the
full "zero retention" pattern, idempotency, and cross-policy isolation
coverage) and a real Docker-based end-to-end run were performed:

1. Assigned a real `retention_days=0, delete_source_media=True,
   delete_derived_media=True, delete_transcript=True` policy to a real
   seeded conversation in a live, restored Postgres database (the same
   one from the restore test above).
2. `docker compose run --rm retention-cleanup run` (dry run, the
   default) — reported "1 conversation evaluated, 2 items that would be
   deleted, 60 bytes that would be freed" and made zero changes;
   confirmed the media file was still present on disk afterward.
3. `docker compose run --rm retention-cleanup run --execute` — reported
   "2 items deleted, 60 bytes freed"; confirmed afterward that the media
   file was genuinely gone from disk, the transcript row was genuinely
   gone from the database (`SELECT` returned `None`), and the
   `MediaAsset` row remained as a tombstone with `deleted_at` set.

See `PHASE_11_VALIDATION_REPORT.md`'s Retention Cleanup section for the
full command transcript.

### Scheduling retention cleanup

This phase ships no in-process scheduler — `docker compose run --rm
retention-cleanup run --execute` is meant to be invoked by an external
scheduler (host cron, a Kubernetes CronJob) at whatever cadence your
retention policies require. A conversation only becomes eligible once
its age passes its policy's `retention_days` threshold, so running this
daily is sufficient for any policy with a threshold measured in days;
size the interval to your most aggressive real policy.
