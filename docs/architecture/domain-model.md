# Domain model (target architecture)

**Status: identity/organizations/audit are now implemented (Phase 1) —
everything else below is still documentation-only target state.** The
`identity`, `organizations`, and `audit` sections describe what actually
exists as of `backend/alembic/versions/0002_identity_rbac.py`; every other
domain remains an empty placeholder package (spec §65: the rest of the
schema ships in later phases) and this document is still the agreed
blueprint for them.

## Target entity list (spec §65)

Grouped by the domain package that will own them (see
`backend/app/<domain>/README.md` for the phase each ships in):

- **identity** (Phase 1 — implemented): `users`, `groups`, `roles`,
  `permissions`, plus the join tables `user_group_memberships`,
  `group_roles`, `role_permissions` that make authorization genuinely
  permission-based (`app.identity.rbac.get_user_permissions`) rather than
  role-name comparisons. `auth_providers` from the original target list is
  not a table — it's the `AuthProvider` interface
  (`app.identity.auth_providers`) plus a `users.auth_provider` enum column
  (`local` implemented; `oidc` / `ldap_ad` / `reverse_proxy` reserved for
  later phases). Sessions are deliberately NOT a table — see
  [ADR-0009](adr/0009-session-storage.md).
- **organizations** (Phase 1 — implemented, foundation only):
  `organizations`, `organization_memberships`. Departmental separation
  within one on-prem install, not SaaS multi-tenancy — org-scoped
  filtering of *other* domains' data ships alongside those domains.
- **audit** (Phase 1 — implemented, `login`/`login_failed`/`logout` events
  only so far): `audit_events` (id, event_type, user_id, username,
  ip_address, user_agent, event_metadata, created_at). General-purpose by
  design — later phases add more `event_type` values, not new tables.
  Hard rule carried forward from the spec: `event_metadata` must never
  contain full conversation content, passwords, tokens, or other secrets.
- **conversations**: `conversations`, `conversation_markers`
- **media**: `media_assets`
- **transcription / diarization**: `speakers`, `transcript_segments`
- **intelligence / evidence**: `extracted_facts`, `fact_evidence`
- **review**: `review_issues`
- **documents**: `documents`, `document_revisions`
- **templates**: `templates`, `template_versions`, `prompts`,
  `prompt_versions`
- **profiles**: `model_profiles`, `model_profile_versions`,
  `processing_profiles`, `processing_profile_versions`
- **workers**: `processing_runs`, `processing_jobs`
- **administration**: `dictionaries`, `dictionary_entries`
- **integrations**: `service_accounts`, `webhooks`, `webhook_deliveries`
- **administration / compliance**: `retention_policies`

## Conversation state machine (spec §22)

Target lifecycle (each transition to be enforced by the `conversations`
domain once implemented):

```
CREATED
  → UPLOADING
  → UPLOADED
  → QUEUED
  → PROCESSING        (drives the 8-stage async worker pipeline)
  → PROCESSED
  → UNDER_REVIEW
  → REVIEWED
  → FINALIZED
  → ARCHIVED
  → DELETED
```

Error/retry states (`FAILED`, `RETRY_PENDING`) branch off `PROCESSING` and
`UPLOADING`; a conversation can be moved to `DELETED` from most states
subject to retention-policy rules (`retention_policies` /
`administration` domain), never a hard SQL DELETE without going through
that lifecycle.

## Evidence types

Every unit of Source content is tagged with exactly one Evidence Type,
which downstream Facts inherit provenance from via `fact_evidence`:

| Evidence Type            | Meaning                                                        |
|---------------------------|------------------------------------------------------------------|
| `EVIDENCE_SPOKEN`          | Said out loud in the recorded conversation, captured via transcription/diarization. |
| `EVIDENCE_USER_CONTEXT`    | Supplied by the user around the conversation (e.g. pre-filled context, form fields) but not spoken. |
| `EVIDENCE_EXTERNAL_SYSTEM`  | Pulled from an integrated external system (spec §'s `integrations` domain / webhooks). |
| `EVIDENCE_MANUAL`          | Manually entered by a reviewer/user directly, not derived from the recording. |
| `UNVERIFIED`               | Not yet reviewed/confirmed — a cross-cutting status, not a source type; anything can start `UNVERIFIED` and move to a verified evidence type through the `review` domain. |

## Source → Facts → Document provenance (the Ramipril example)

This is the concrete illustration from spec §4 of why the three-layer model
(ADR-0004) matters:

1. **Source**: a `transcript_segment` captures the doctor saying "Ich
   verschreibe Ihnen Ramipril, fünf Milligramm" — tagged
   `EVIDENCE_SPOKEN`, with exact start/end timestamps and the speaker who
   said it.
2. **Facts**: the `intelligence` domain extracts an `extracted_fact` —
   structured as something like `{ type: "medication", name: "Ramipril",
   dose: "5mg" }` — and records a `fact_evidence` row linking that fact to
   the exact `transcript_segment` above (not to the whole conversation, not
   to a paraphrase).
3. **Document**: when a `document` (e.g. a visit summary) is generated, the
   sentence "Patient is prescribed Ramipril 5mg" is composed *from* the
   `extracted_fact`, and the document retains the chain back to
   `fact_evidence` → `transcript_segment`. A reviewer opening that sentence
   in the `review` domain can always jump to the exact spoken moment that
   justifies it — nothing in the document is LLM-invented without a
   traceable Source.

This chain (Source → Facts → Document, all provenance-linked) is the
non-negotiable core of "evidence-based" in the product name, and every
future domain's schema must preserve it — a Fact without `fact_evidence`,
or a Document statement that can't be traced to a Fact, is a modeling bug.
