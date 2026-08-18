# Admin: retention

See [ADR-0015](../architecture/adr/0015-retention-and-deletion-semantics.md)
for the full design rationale.

## What exists today

`RetentionPolicy` rows (name, `retention_days`, `delete_source_media`,
`delete_derived_media`, `active`) can be created directly against the
database (no admin UI yet — Phase 7) and assigned to a `Conversation` via
its `retention_policy_id` FK. **No scheduler reads or acts on these
policies in Phase 2** — assigning a policy today records intent only.

`Settings.default_retention_policy_name`
(`VOCADOX_DEFAULT_RETENTION_POLICY_NAME`) is unset by default, meaning
every new conversation without an explicitly assigned policy is
implicitly "keep indefinitely." This is a deliberate default, not an
oversight — VocaDox does not choose a retention period on your
organization's behalf.

## What operators must decide

If your deployment has a legal or organizational obligation to delete
conversation data after a fixed period, you must:
1. Create the appropriate `RetentionPolicy` row(s) for your requirements.
2. Assign them to conversations (via the API, until an admin UI exists).
3. Understand that **enforcement (actually deleting data on schedule) is
   not implemented yet** — until a scheduler ships in a later phase, you
   are responsible for manual or externally-scripted enforcement if you
   need it now.

**Do not treat the existence of the `retention_policies` table as a GDPR
or other regulatory compliance guarantee by itself.** It is a data-model
foundation, not a compliance feature.

## Manual deletion today

Until a scheduler exists, `DELETE /conversations/{id}` (or the UI's
Delete action) is the only way to actually remove a conversation's media —
see `docs/architecture/conversations.md`, "Deletion semantics."
