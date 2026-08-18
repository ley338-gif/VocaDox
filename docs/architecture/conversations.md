# Conversations domain (Phase 2)

## Entities

`Conversation` (`backend/app/conversations/models.py`) is the logical
container: id, organization_id, created_by_user_id, title, description,
`conversation_type`, `status`, started_at/ended_at/duration_ms,
external_reference(+type), `privacy_mode`, retention_policy_id, timestamps,
soft-delete `deleted_at`. It never holds media bytes — see
[ADR-0011](adr/0011-source-media-separation.md).

`ConversationType` (GENERAL/MEDICAL/THERAPY/MEETING/INTERVIEW/OTHER) is an
organizational/documentation hint only — it never gates or implies AI
behavior. `PrivacyMode` (STANDARD/RESTRICTED) is likewise represented now
so the schema doesn't need to change later (see "Privacy mode" below).

Related entities, all FK'd to `conversation_id`:
- `ConversationParticipant` — display_name (free-form label, never a
  required real name), `participant_type`, optional external_reference/
  notes. No automatic speaker-to-participant mapping exists or is planned
  before Phase 3's diarization ships with human review.
- `ConversationMarker` — timestamp_ms, optional label/note. A manual
  bookmark, not AI Evidence.
- `ConversationNote` — content, optional timestamp_ms. Conceptually
  `EVIDENCE_USER_CONTEXT` for the future Evidence engine (see
  `docs/architecture/domain-model.md`) but the Evidence engine itself does
  not exist yet.
- `RetentionPolicy` — see "Retention" below.

## Conversation state machine

Centralized in `app.conversations.state_machine` — the *only* place that
decides whether `status = X` is legal. States that genuinely exist in
Phase 2:

```
CREATED → RECORDING → UPLOADED → NORMALIZING → READY
        ↘ UPLOADED (file-upload path skips RECORDING)
Any of the above (except DELETED) → FAILED → UPLOADED (retry) or DELETED
Any non-DELETED state → DELETED
```

`TRANSCRIBING`/`DIARIZING`/`EXTRACTING`/`APPROVED` from
`docs/architecture/domain-model.md`'s target-architecture list are
deliberately **not** members of `ConversationStatus` in Phase 2 — asserted
directly in `tests/conversations/test_state_machine.py::
test_created_to_transcribing_does_not_exist`, so a future PR can't
reintroduce them by accident before their own phase is approved.

No route or service function assigns `conversation.status` directly;
everything goes through `app.conversations.service.apply_status_transition`,
which delegates to `state_machine.transition` and raises
`InvalidTransitionError` on an illegal move.

## Privacy mode: what's implemented, what isn't

`privacy_mode` is a real column, checked in API responses and settable at
creation/update time. What is **not** implemented in Phase 2: any
*additional* access restriction beyond ordinary
Permission + Organization Membership + Conversation's Organization for a
`RESTRICTED` conversation (e.g. narrowing to specific users within the
same organization). Treat `RESTRICTED` today as a visible flag/signal for
operators and future UI, not an enforced narrower ACL — that's explicitly
deferred, not silently missing.

## Retention: what's implemented

See [ADR-0015](adr/0015-retention-and-deletion-semantics.md). The
`retention_policies` table and FK exist; no scheduler applies them yet.
`retention_days = NULL` (keep indefinitely) is the default for any
conversation without an assigned policy — a conscious choice documented in
`docs/admin/retention.md`, not a GDPR compliance claim.

## Deletion semantics

`DELETE /conversations/{id}` soft-deletes the `Conversation` row
(`deleted_at` set, `status → DELETED`) **and**, in the same
request/transaction, physically destroys every non-deleted `MediaAsset`'s
bytes via `StorageProvider.delete`, marking each `MediaAsset.deleted_at`
too. See ADR-0015 for the full rationale and consequences (no undelete,
synchronous, reuses the same helper future retention scheduling can call).

## Organization ownership & authorization

Every Conversation belongs to exactly one Organization
(`organization_id`, FK `CASCADE`). `app.conversations.authz.
authorize_conversation_access` is the single choke point every
conversation/media/participant/marker/note endpoint calls: Permission +
Organization Membership + Conversation's Organization, `system:admin`
bypassing only the membership check (not the permission check). See
`docs/security/threat-model.md` §7 for the security properties this
guarantees and how they're tested.

## Permissions

`conversation:{create,read,update,delete,record,upload,
manage-participants,manage-notes,manage-markers}`, `media:{read,upload,
delete}` — seeded via `app.identity.seed` (extends Phase 1's RBAC seed,
same idempotent `apply_seed` mechanism) and assigned to the built-in
`User`/`Manager`/`Reviewer`/`API Service Account`/`System Admin` roles. See
`backend/app/identity/seed.py` for the exact per-role grant list.
