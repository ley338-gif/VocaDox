# Admin: retention

See [ADR-0015](../architecture/adr/0015-retention-and-deletion-semantics.md)
for the full design rationale.

## What exists today

`RetentionPolicy` rows (name, `retention_days`, `delete_source_media`,
`delete_derived_media`, `delete_transcript`, `active`) can be created/
edited via the Phase 7 Admin Portal (`/admin/retention`, gated by
`retention:read`/`retention:write`) or its REST API (`GET/POST
/admin/retention-policies`, `PATCH /admin/retention-policies/{id}`) and
assigned to a `Conversation` via its `retention_policy_id` FK.

**As of Phase 11, enforcement exists but is not self-scheduling.**
`app.cli.retention_cleanup` (also reachable via `POST
/admin/retention-cleanup/run`, gated by `retention-cleanup:trigger`, and
`docker compose run --rm retention-cleanup run [--execute]`) evaluates
every active policy against its assigned conversations and deletes
expired source/derived media and/or transcripts (dry-run by default; a
full item-level audit trail is recorded in `RetentionCleanupRun`/
`RetentionCleanupItem`, viewable via `retention-cleanup:read`). **Nothing
in this codebase calls it automatically** — no in-process scheduler,
cron, or Kubernetes CronJob ships with VocaDox itself. An operator who
needs retention actually enforced on a schedule must wire up their own
external trigger (host cron, `systemd` timer, or k8s CronJob invoking the
CLI/API above) — see `docs/architecture/future-considerations.md`'s
"Phase 11 additions" and `PHASE_12_VALIDATION_REPORT.md`'s Retention
Audit for the full disposition of this gap.

`Settings.default_retention_policy_name`
(`VOCADOX_DEFAULT_RETENTION_POLICY_NAME`) is unset by default, meaning
every new conversation without an explicitly assigned policy is
implicitly "keep indefinitely." This is a deliberate default, not an
oversight — VocaDox does not choose a retention period on your
organization's behalf.

## What operators must decide

If your deployment has a legal or organizational obligation to delete
conversation data after a fixed period, you must:
1. Create the appropriate `RetentionPolicy` row(s) via `/admin/retention`.
2. Assign them to conversations (a Processing Profile version's
   `retention_policy_id`, or directly via the conversation API).
3. Configure an **external scheduler** (cron/systemd timer/k8s CronJob)
   to invoke `docker compose run --rm retention-cleanup run --execute`
   (or the equivalent API call) on whatever cadence your obligation
   requires — VocaDox enforces policies correctly once triggered, but
   nothing triggers it on your behalf.

**Do not treat the existence of the `retention_policies` table as a GDPR
or other regulatory compliance guarantee by itself.** It is a data-model
foundation, not a compliance feature.

## Manual deletion today

Until an external scheduler is configured to run the Retention Cleanup
CLI/API on your behalf, `DELETE /conversations/{id}` (or the UI's Delete
action) remains the only way to *immediately* remove a specific
conversation's media on demand — see
`docs/architecture/conversations.md`, "Deletion semantics."
