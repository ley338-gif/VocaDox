# Admin: retention

See [ADR-0015](../architecture/adr/0015-retention-and-deletion-semantics.md)
for the full design rationale.

## What exists today

`RetentionPolicy` rows (name, `retention_days`, `delete_source_media`,
`delete_derived_media`, `active`) can be created/edited via the Phase 7
Admin Portal (`/admin/retention`, gated by `retention:read`/
`retention:write`) or its REST API (`GET/POST /admin/retention-policies`,
`PATCH /admin/retention-policies/{id}`) and assigned to a `Conversation`
via its `retention_policy_id` FK. **No scheduler reads or acts on these
policies** — assigning a policy today records intent only; the admin UI
manages the policy definitions, it does not enforce them. Automated
enforcement (a "Retention Cleanup" worker that actually deletes expired
data) is Phase 11 scope, not implemented here.

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
3. Understand that **enforcement (actually deleting data on schedule) is
   not implemented yet** — until the Phase 11 Retention Cleanup worker
   ships, you are responsible for manual or externally-scripted
   enforcement if you need it now.

**Do not treat the existence of the `retention_policies` table as a GDPR
or other regulatory compliance guarantee by itself.** It is a data-model
foundation, not a compliance feature.

## Manual deletion today

Until a scheduler exists, `DELETE /conversations/{id}` (or the UI's
Delete action) is the only way to actually remove a conversation's media —
see `docs/architecture/conversations.md`, "Deletion semantics."
