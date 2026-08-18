# Domain model (target architecture)

**Status: documentation only.** None of the entities below exist as
database tables in Phase 0 (spec §65: the domain schema starts Phase 1 —
`backend/alembic/versions/0001_baseline.py` is intentionally a no-op). This
document describes the target-state model so Phase 1+ implementation has an
agreed blueprint, and so each domain package's placeholder README can point
here for "what will eventually live in this package."

## Target entity list (spec §65)

Grouped by the domain package that will own them (see
`backend/app/<domain>/README.md` for the phase each ships in):

- **identity**: `users`, `groups`, `roles`, `permissions`, `auth_providers`
- **organizations**: `organizations`, `organization_memberships`
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
- **audit**: `audit_events`

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
