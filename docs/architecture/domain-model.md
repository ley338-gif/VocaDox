# Domain model (target architecture)

**Status: identity/organizations/audit (Phase 1), conversations/media
(Phase 2), transcription/diarization (Phase 3), intelligence/evidence/
review/profiles-foundation (Phase 4), and documents/review-wizard/
approval (Phase 5) are now implemented — everything else below is still
documentation-only target state.** The `identity`, `organizations`, and
`audit` sections describe what exists as of
`backend/alembic/versions/0002_identity_rbac.py`; `conversations` and
`media` describe what exists as of
`backend/alembic/versions/0003_conversation_capture.py`;
`transcription`/`diarization` as of
`backend/alembic/versions/0004_speech_diarization.py`; `intelligence`/
`evidence`/`review`/the `model_profiles` foundation as of
`backend/alembic/versions/0006_intelligence_evidence.py`; `documents` (plus
extensions to `intelligence`/`review`) as of
`backend/alembic/versions/0007_documents_review.py` (see
`docs/architecture/conversations.md`, `docs/architecture/media-storage.md`,
`docs/architecture/media-ingestion.md`,
`docs/architecture/intelligence-pipeline.md`,
`docs/architecture/evidence-model.md`, `docs/architecture/documents.md`
for the full detail — this document stays the high-level index). Every
other domain remains an empty placeholder package (spec §65: the rest of
the schema ships in later phases) and this document is still the agreed
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
- **conversations** (Phase 2 — implemented): `conversations`,
  `conversation_participants`, `conversation_markers`,
  `conversation_notes`, `retention_policies`. State machine intentionally
  limited to states that genuinely exist (CREATED/RECORDING/UPLOADED/
  NORMALIZING/READY/FAILED/DELETED) — see
  `docs/architecture/conversations.md`.
- **media** (Phase 2 — implemented): `media_assets`, `recording_uploads`.
  Source media is immutable, SHA-256-verified, and never overwritten by
  normalization — see `docs/architecture/media-storage.md` and
  `docs/architecture/media-ingestion.md`. No AI/transcription/diarization
  of any kind exists yet.
- **transcription / diarization**: `speakers`, `transcript_segments`
- **intelligence / evidence** (Phase 4 — implemented): `extracted_facts`,
  `fact_evidence`. See `docs/architecture/intelligence-pipeline.md` and
  `docs/architecture/evidence-model.md` for the full detail.
- **review** (Phase 4 read-only surface; Phase 5 Review Wizard —
  implemented): `review_issues`, now with real resolution fields
  (`resolved_status`/`resolved_fact_id`/`resolved_by_user_id`/
  `resolved_at`) written by `PATCH /conversations/{id}/review-issues/
  {issue_id}`. See `docs/architecture/documents.md`.
- **documents** (Phase 5 — implemented): `documents`, `document_revisions`.
  Composition/revisions/approval workflow — see
  `docs/architecture/documents.md`. The full Template Engine
  (`templates`/`template_versions`) remains Phase 6.
- **templates**: `templates`, `template_versions`, `prompts`,
  `prompt_versions`
- **profiles** (Phase 4 — `model_profiles` implemented as a minimal
  foundation; Phase 6 — versioned, admin-manageable, plus
  `processing_profiles`/`processing_profile_versions`; Phase 8 — adds
  `model_profiles.lifecycle_status` (spec §51: AVAILABLE/TESTING/PILOT/
  PRODUCTION/RETIRED) and `model_profile_lifecycle_events`, an append-only
  transition audit trail): full entity list is `model_profiles`,
  `model_profile_versions`, `model_profile_lifecycle_events`,
  `processing_profiles`, `processing_profile_versions`. See
  `docs/architecture/future-considerations.md`.
- **analytics** (Phase 8 — implemented): technical/quality/correction
  analytics are computed on read from existing tables (no new table);
  `evaluation_runs` (spec §50: one row per Evaluation Lab model/prompt
  comparison run, storing only ids/config/counts, never fixture or
  conversation content) is the one new table. See
  `docs/admin/analytics-evaluation.md`.
- **workers**: `processing_runs`, `processing_jobs`
- **administration** (Phase 7 — admin surface implemented; `dictionaries`/
  `dictionary_entries` remain undelivered, deferred per roadmap §73/spec
  mockup — see `docs/architecture/future-considerations.md`'s Phase 7
  additions): `dictionaries`, `dictionary_entries`
- **integrations** (Phase 10 — implemented): `service_accounts`,
  `webhooks`, `webhook_deliveries`. Service accounts authenticate via API
  key (Argon2id-hashed secret, reusing `app.identity.passwords`) and are
  authorized via the *same* `permissions.code` vocabulary Phase 1's RBAC
  already defines (a service account's `scopes` column is a list of those
  same codes) — not a parallel scope system. Webhooks fire from the exact
  audit event types already emitted by Phases 1-9
  (`app.integrations.service.WEBHOOK_EVENT_TYPES`), HMAC-SHA256 signed,
  bounded-retry, delivery-logged. See
  `docs/architecture/future-considerations.md`'s "Phase 10 additions" for
  the REST Integration API's scope decision and the FHIR/HL7/PVS/KIS/CRM/
  Meeting-Platform adapter architecture (documentation-only, per roadmap
  §73 — no such adapter is implemented).
- **administration / compliance** (Phase 7 — admin CRUD implemented over
  the model, which has existed since Phase 2; no automated enforcement
  scheduler yet, see `docs/admin/retention.md`): `retention_policies`

## Conversation state machine (spec §22)

**Note:** this is still the full *target* lifecycle spanning every future
phase. Phase 2's actual, implemented state machine
(`app.conversations.state_machine`) only covers the CREATED → RECORDING/
UPLOADED → NORMALIZING → READY (+ FAILED/DELETED) subset that genuinely
exists today — see `docs/architecture/conversations.md` for the real
state diagram. TRANSCRIBING/DIARIZING/EXTRACTING/etc. below remain
documentation-only until their own phase is approved.

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

## Phase 9: Longitudinal Documentation (spec §39/§40/§41)

Timeline/external-reference grouping, comparison, and Follow-ups/Tasks are
built on two entities that already existed before this phase — no new
grouping key or parallel fact type was invented:

- **Grouping key**: `conversations.external_reference` (Phase 2). Multiple
  `Conversation`s sharing the same `(organization_id, external_reference)`
  compound key form one Timeline. `external_reference` alone is never a
  valid scoping key — two organizations can coincidentally use the same
  reference string (e.g. both numbering cases "1", "2", "3", ...), so
  every Timeline/Comparison query in `app.longitudinal.service` filters on
  the compound key, never on `external_reference` in isolation.
- **Comparison** (`app.longitudinal.comparison`): a real, deterministic,
  structural comparison over `extracted_fact` rows of `category
  ="general_fact"` across a Timeline's conversations, oldest-first —
  never an LLM asked to summarize "what changed" (spec §40's explicit
  "Keine unbelegte Interpretation von Aenderungen"). It reuses
  `app.intelligence.contradictions.detect_contradictions` verbatim for
  same-conversation contradictions (-> `CONTRADICTED`) and adds a
  cross-conversation temporal diff for the same normalized
  (subject, attribute) pair (-> `NEW`/`CHANGED`/`NOT_MENTIONED`). Every
  result carries the fact id(s) of both sides being compared.
- **Follow-ups/Tasks** (`app.longitudinal.models.FollowUpTask`): a
  generic, domain-neutral action item. `AI_EXTRACTED` rows are
  idempotently synced from Phase 4's existing `extracted_facts(category=
  "task")` rows (no parallel fact type) and always carry `source_fact_id`
  back to the originating fact; `USER_CREATED` rows are added directly by
  a human, `source_fact_id` is NULL. No notification/reminder/email system
  exists here (Phase 10 territory).
