# 0015 — Retention foundation and soft-delete vs. physical deletion

## Status
Accepted

## Context
The brief requires the schema to support retention-policy assignment
(without a scheduler yet) and requires that a soft-deleted `Conversation`
row with audio still on disk not count as "deleted" from a privacy
standpoint.

## Decision
`RetentionPolicy` (id, name, `retention_days` optional, `delete_source_media`,
`delete_derived_media`, `active`) exists as a real table with a real FK from
`conversations.retention_policy_id`, but **no scheduler executes it** —
Phase 2 ships the data model and manual-deletion path only. `retention_days
= NULL` means "keep indefinitely," which is the explicit default for any
conversation not assigned a policy (`Settings.default_retention_policy_name`
defaults to unset). This is a conscious default, not an accidental one —
`docs/admin/retention.md` tells operators plainly that VocaDox does not
choose a retention period for them and that leaving this unset is itself a
decision with compliance implications for their deployment.

Deletion (`DELETE /conversations/{id}`) is a single operation with two
effects, both real, neither cosmetic:
1. `conversations.deleted_at` is set and `status` transitions to
   `DELETED` (soft delete — the row and its audit trail survive).
2. Every non-deleted `MediaAsset` under that conversation has its physical
   bytes destroyed via `StorageProvider.delete` **and** `deleted_at` set on
   the `MediaAsset` row itself, in the same request
   (`app.conversations.service.soft_delete_conversation`).

`GET`/list endpoints filter `deleted_at IS NULL` everywhere a Conversation
or MediaAsset is looked up, so a soft-deleted conversation is unreachable
through the normal API immediately — but the row (metadata only, never
audio bytes) persists for audit purposes.

## Alternatives considered
- **Hard `DELETE` from Postgres.** Rejected — destroys the audit trail
  (`audit_events` reference `conversation_id`/`media_id` only loosely via
  JSON metadata, not FKs, but the Conversation row itself is the anchor a
  human investigating "what happened to this recording" would look for)
  and conflicts with the brief's "retain only minimal justified audit
  metadata" instruction, which implies *something* survives.
- **Soft-delete only, physical bytes retained until a background sweep.**
  Rejected — this is exactly the "soft-deleted DB record with audio still
  on disk isn't actually deleted" anti-pattern the brief calls out by
  name. Physical destruction happens synchronously, in the same request,
  not on a best-effort timer.
- **A full retention scheduler in Phase 2.** Out of scope — the brief is
  explicit "that's later." The schema is ready for it; nothing about
  adding a scheduler later requires a data-model change.

## Consequences
- Deletion is synchronous and can be slow for a conversation with a very
  large source file (storage delete is a single `unlink`, so this is
  expected to be fast in practice, but is not chunked/backgrounded).
- There is currently no "undelete" — once `soft_delete_conversation` runs,
  the physical media is genuinely gone, matching "never retain audio
  secretly," but also meaning a delete confirmed in error is unrecoverable
  (the frontend requires an explicit confirm dialog for this reason).
- A future retention scheduler can reuse `soft_delete_conversation`
  directly once it exists, rather than reimplementing the
  destroy-then-mark-deleted sequence.
