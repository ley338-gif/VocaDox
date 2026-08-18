# Phase 2 Validation Report — Conversation Capture & Media Foundation

## Executive Summary

Phase 2 delivers the trusted source-media layer VocaDox's future
transcription/diarization/evidence phases will build on: real
`Conversation`/`MediaAsset`/`ConversationParticipant`/`ConversationMarker`/
`ConversationNote`/`RetentionPolicy` domain models, a centralized
conversation state machine limited to states that genuinely exist, SHA-256
-verified immutable source media on namespaced opaque storage keys,
streaming upload validation, an idempotent browser-recording finalize
flow, organization-scoped REST + RBAC, and a functional frontend
(conversations list/new/detail, a real MediaRecorder-based recording
workspace with consent gating, an audio player with markers). No
speech-to-text, diarization, summarization, or Evidence/document
generation exists anywhere in this codebase — verified by grep, not just
by intent (see "Explicitly forbidden" checks below).

Two real bugs were found and fixed via genuine testing (not just code
review) before merge: a CSRF-token-recovery gap that silently blocked
every mutating action after a page reload (browser testing), and a
non-root container permission error on first media upload (fresh Docker
install testing). Both are documented in their own commits and below.

**Recommendation: GO for Phase 3**, with the residual risks and deferred
items below explicitly accepted, not hidden.

## Scope

Implemented: Conversation domain + state machine, MediaAsset ingestion
(browser recording + file upload converging on one pipeline), SHA-256
source integrity, namespaced opaque storage, upload validation
(magic-byte sniffing, size caps, streaming), participants/markers/notes
CRUD, organization-scoped authorization, RBAC permission extensions,
retention-policy data model (no scheduler), soft-delete + physical media
destruction, audit events, REST API, OpenAPI, frontend UI, recording
consent UX, docs, ADRs, threat-model updates.

Explicitly NOT implemented (verified absent): Whisper/faster-whisper, any
STT, pyannote/diarization, Qwen/Ollama/vLLM, speaker-identification AI,
summarization, fact extraction, Evidence generation, document generation,
clinical interpretation, calls to any cloud AI/transcription provider.
`compliance/model-inventory.yml` remains empty (0 models).

## Architecture

`Conversation` → `MediaAsset` (SOURCE_AUDIO / NORMALIZED_AUDIO /
ATTACHMENT) → (future Transcript) → (future Evidence). See
[ADR-0011](docs/architecture/adr/0011-source-media-separation.md). Full
detail in `docs/architecture/conversations.md`,
`docs/architecture/media-storage.md`, `docs/architecture/media-ingestion.md`.

## Conversation Domain

`Conversation`, `ConversationParticipant`, `ConversationMarker`,
`ConversationNote`, `RetentionPolicy` — all real SQLAlchemy models,
migrated via `0003_conversation_capture.py`. UUIDs throughout.
`ConversationType` (GENERAL/MEDICAL/THERAPY/MEETING/INTERVIEW/OTHER) is
organizational metadata only — grep-verified no code path branches AI
behavior on it.

## Conversation State Machine

`app.conversations.state_machine` centralizes every transition;
`ConversationStatus` = CREATED/RECORDING/UPLOADED/NORMALIZING/READY/
FAILED/DELETED only — `tests/conversations/test_state_machine.py::
test_created_to_transcribing_does_not_exist` asserts
TRANSCRIBING/DIARIZING/EXTRACTING/APPROVED are not members of the enum.
11 unit tests cover valid/invalid transitions, retry-from-FAILED, and
DELETED as terminal/reachable-from-anywhere.

## Media Architecture

`MediaAsset` covers both source and derived media via `kind`; a derived
asset is always a new row (`derived_from_media_id` FK), never an in-place
rewrite. `RecordingUpload` tracks idempotent recording-finalize sessions.
See ADR-0011, ADR-0013.

## Browser Recording

`getUserMedia` + `MediaRecorder` via `frontend/src/recording/useRecorder.ts`,
feature-detected (`isRecordingSupported()`), consent-gated
(`RecordingWorkspace.tsx`), with elapsed time, a live level meter
(`AnalyserNode`), pause/resume, markers, stop, discard, and finalize/
upload. Never auto-starts (verified by unit test). The pure state
machine (`recordingMachine.ts`) is unit tested directly — 12 tests
covering permission-denied/recovery, pause/resume, MediaRecorder error,
device disconnect, accidental double-stop, upload failure/retry,
duplicate-finalize no-op, discard, and the navigation-away-warning
predicate — since jsdom has no real `MediaRecorder` to exercise
end-to-end in an automated test.
**Status: PARTIALLY VERIFIED.** The state machine and UI wiring are
unit-tested and were exercised manually in a real browser (Chrome, via
the Claude Browser tool) through the consent screen and permission flow;
actual microphone capture was not exercised in that session (no
microphone device available in the automated browser environment) — the
finalize/upload path was instead verified end-to-end via the file-upload
path and via `POST .../recordings` API tests using synthetic audio bytes
(`tests/conversations/test_api.py::test_recording_finalize_is_idempotent`).

## File Upload

Converges on the same `ingest_media` pipeline as recording. Verified in
a real browser session: conversations list → new conversation → detail
page → participant added, and separately end-to-end via a Python script
against the real Docker-composed backend (login → create conversation →
upload synthetic WAV → SHA-256 verified → play/download → hash matches).

## Upload Reliability

Streaming spool with size-cap enforcement as bytes arrive
(`app.media.service.spool_upload`), never buffers the full payload.
Chunked upload-during-recording was evaluated and deferred in favor of an
idempotent single-request finalize — see
[ADR-0012](docs/architecture/adr/0012-chunked-upload-decision.md) for the
full trade-off analysis and the honestly-documented limitation (an active
recording is lost on browser/tab crash; a *completed* recording's upload
is retry-safe).

## Media Validation

Magic-byte sniffing (`app.media.validation.sniff_audio_format`) against
WebM/Opus, WAV, MP3, M4A only. Empty files, oversize files, and
unrecognized formats (including HTML/script content) rejected with 422.
Client-supplied Content-Type never trusted alone.

## Source Integrity

SHA-256 computed once at ingestion, persisted, never recomputed. See
"Source Integrity Validation" below for the live result.

## Storage

`LocalFilesystemStorage` extended with namespaced opaque keys
(`data/organizations/<org>/conversations/<conv>/{source,derived,
attachments}/<uuid>`) — see ADR-0013. Storage root/temp dir configurable
via `VOCADOX_MEDIA_STORAGE_ROOT`/`VOCADOX_UPLOAD_TEMP_DIR`. No hardcoded
paths in domain code (architecture-boundary tests unchanged/passing).

## Normalization

`MediaNormalizer` abstraction; only `NoOpMediaNormalizer` ships. No
FFmpeg or other tool was evaluated or used. `mutagen` was evaluated for
metadata extraction and **rejected** (see below). See
[ADR-0014](docs/architecture/adr/0014-media-normalization-and-metadata.md).

## Participants / Markers / Notes

Full CRUD, org-scoped authorization, audit events. `display_name` never
requires a real name. No automatic speaker-to-participant mapping exists.

## Organization Isolation

Hard-tested security property. `app.conversations.authz.
authorize_conversation_access` is the single choke point: Permission +
Organization Membership + Conversation's Organization, `system:admin`
bypassing membership only. Wrong-organization access returns 404, never
403 (no existence leak). Tests:
`test_cross_organization_uuid_guessing_is_denied`,
`test_media_access_denied_across_organizations`,
`test_system_admin_can_access_any_organization_conversation`,
`test_missing_permission_is_denied`,
`test_unauthenticated_request_is_denied`,
`test_list_conversations_only_shows_own_organization`,
`test_user_only_sees_own_organizations` /
`test_admin_sees_all_organizations`.

## Authorization

New permissions: `conversation:{create,read,update,delete,record,upload,
manage-participants,manage-notes,manage-markers}`, `media:{read,upload,
delete}`, seeded via the existing idempotent `apply_seed` mechanism and
assigned to `User`/`Manager`/`Reviewer`/`API Service Account`/
`System Admin`. `python -m app.identity.seed` added as the Phase 1→2
upgrade path (no manual SQL).

## Privacy

`PrivacyMode.STANDARD`/`RESTRICTED` modeled; RESTRICTED does not yet
narrow access beyond ordinary org+permission checks — documented as a
known gap in `docs/architecture/conversations.md`, not silently missing.

## Retention

`RetentionPolicy` table + FK exist; no scheduler executes them.
`retention_days = NULL` (keep indefinitely) is the explicit default — see
[ADR-0015](docs/architecture/adr/0015-retention-and-deletion-semantics.md).
No GDPR-compliance claim made from this alone.

## Deletion

Soft-delete (`deleted_at`, `status → DELETED`) + synchronous physical
media destruction in the same request — verified via API test
(`test_deleting_conversation_physically_removes_media`): after delete,
both the conversation and its media content return 404.

## Frontend

`/app/conversations` (list, search, status/type filters, pagination),
`/app/conversations/new` (record/upload choice), `/app/conversations/:id`
(Overview/Audio/Participants/Notes/Activity tabs — no Transcript/Summary/
Evidence tabs present at all). Audio player with marker overlay. Verified
live in a real browser: login → new conversation → recording-consent
screen → participants tab → add "Person A" → conversations list shows the
new row with correct status/type/privacy/date.

## API / OpenAPI

All Phase 2 endpoints under `/api/v1`, documented in OpenAPI, TS client
regenerated, CI drift gate passing (`OpenAPI TS client drift check`
green). No manually duplicated Conversation interfaces on the frontend.

## Database / Migrations

`0003_conversation_capture.py`: `conversations`, `media_assets`,
`conversation_participants`, `conversation_markers`, `conversation_notes`,
`retention_policies`, `recording_uploads`. Indexes on organization_id,
created_by_user_id, status, created_at, external_reference, every
conversation_id FK, media kind/sha256/created_at. Timezone-aware
timestamps throughout. `downgrade()` verified against real Postgres
(see below).

## Audit

`conversation.{created,updated,recording_started,recording_completed,
uploaded,deleted}`, `conversation.participant_{added,updated,removed}`,
`conversation.marker_{created,updated,deleted}`, `conversation.
note_{created,updated,deleted}`, `media.{created,downloaded,deleted}` —
all implemented, verified in `test_audit_events_recorded_for_
conversation_lifecycle` including a spot-check that metadata never
contains raw title/content.

## Security

`docs/security/threat-model.md` §7 and two new docs
(`docs/security/media-security.md`, `docs/security/recording-privacy.md`)
cover malicious media, path traversal, filename injection, cross-org
IDOR, storage exhaustion (residual risk, documented), abandoned uploads,
consent/mic misuse, temp-file handling, source tampering, deletion
failures.

## Compliance

No new runtime dependency added this phase (`mutagen` was evaluated and
rejected — GPL-2.0-or-later per a live PyPI JSON API lookup, not assumed
— see ADR-0014; direct-dependency count is unchanged from Phase 1).
License compliance CI job (direct + full transitive tree, regenerated and
diffed against committed inventory) passed with **0 drift**.

## Dependencies / Licenses

- Direct (Python + Node): unchanged from Phase 1 — all Approved.
- Transitive: regenerated by CI against the actual resolved trees; CI's
  "Fail if the regenerated transitive inventory drifted" step passed
  (no drift), meaning the committed inventory is still accurate.
- Containers: unchanged base images from Phase 0/1 (postgres:16.6-alpine,
  valkey:8.0.2-alpine, python:3.11-slim-trixie, node build image) — no new
  image introduced.
- Models: 0 (unchanged) — Phase 2 is intentionally AI-free.

All buckets: **0 Blocked, 0 Unknown** (CI's license-compliance job passed;
UNKNOWN=BLOCKED policy enforced).

## Tests

- **Backend: 107 passed**, 0 failed (`pytest`, real run against
  Postgres-backed logic where applicable, SQLite for fast unit/API
  tests — matches existing project convention).
- **Frontend: 21 passed**, 0 failed (`vitest`), including 12 new
  recording-state-machine unit tests.
- **E2E**: no dedicated E2E framework exists in this project yet (Phase 0/1
  didn't add one). Per the brief's fallback, the cross-org authorization
  scenario and the full login→create→upload→play→participant→marker→note
  flow were both verified at the API level (backend test suite) AND
  manually end-to-end against the real, Docker-composed stack (see
  "Fresh Install" and "Restart Persistence" below) — not simulated.

ruff, mypy, eslint, tsc: all clean (0 findings) as of the merged commit.

## GitHub Actions

**PASS.** All 7 CI jobs green on the final commit before merge (run
32126761286): Docker build, Backend (lint/typecheck/test), Frontend
(lint/typecheck/test/build), License compliance, OpenAPI TS client drift
check, Container vulnerability scan (Trivy), Alembic migration (real
Postgres). Two intermediate CI failures were hit and fixed before merge
(ruff line-length on the alembic migration file scanned by `ruff check .`
from `backend/`, not caught by a narrower local `ruff check app tests`)
— documented in the branch's commit history rather than force-pushed away.

## Fresh Install

**PASS.** `docker compose down -v && docker compose build --no-cache &&
docker compose up -d`: all 4 services (postgres, valkey, backend,
frontend) started and became healthy. `alembic upgrade head` applied
cleanly inside the fresh container. `bootstrap_admin` created the first
System Admin. Full flow verified via a script hitting the real running
API: login → create conversation → upload synthetic WAV → SHA-256
verified on response → play/download → SHA-256 verified again →
add participant → add marker → add note — every step 200/201.

**One real bug found and fixed during this validation** (not
theoretical): the first media upload against the freshly built image
500'd with `PermissionError: [Errno 13] Permission denied: 'data'` — the
backend container runs as a non-root user (`vocadox`) but `/app` (built
as root) had no writable `data/` directory. Fixed in `backend/Dockerfile`
(pre-create + chown the directory before `USER vocadox`) and
`deploy/docker-compose.yml` (added a named `vocadox_backend_data` volume
so media survives container recreation, not just in-place restart).
Re-verified after the fix: full flow above passed clean on a rebuilt
image.

## Upgrade Validation

**PASS.** Against real Postgres: `alembic downgrade base` →
`alembic upgrade 0002_identity_rbac` (Phase 1 schema) →
`python -m app.identity.bootstrap_admin` (Phase-1-style admin created) →
`alembic upgrade head` (Phase 2 schema, no manual SQL) →
`python -m app.identity.seed` (idempotent RBAC reseed) → verified via a
script that the pre-existing admin user is intact, active, and now holds
every new `conversation:*`/`media:*` permission it should have per its
`System Admin` role. No manual SQL at any step.

## Restart Persistence

**PASS.** Against the fresh-install stack: created a conversation,
uploaded a synthetic WAV (SHA-256 recorded), added a participant/marker/
note, then `docker compose restart` (all 4 containers). After restart:
conversation metadata intact, media list intact with matching SHA-256,
`GET .../content` playback returned bytes whose SHA-256 matched exactly,
and all 3 of participant/marker/note survived. Verified via the real
running API, not inferred from code.

## Source Integrity Validation

**PASS**, recorded exact result. Client-computed SHA-256 of a synthetic
WAV before upload: `c4a948f325d39c925685c2f91f30453f46903bf6e1826eed691cbd8f86643061`.
Server-returned `media_assets.sha256` immediately after ingestion: same
value (`upload media True`). Recomputed SHA-256 of the bytes retrieved via
`GET .../content` immediately after upload: same value
(`play/download True`). Recomputed again after a full 4-container
`docker compose restart`: same value (`playback after restart True`). All
three checkpoints (pre-ingestion, post-ingestion, post-restart) matched
exactly — zero divergence.

Earlier in the session, the same three-way check was additionally run
directly against a persistent local Postgres+filesystem setup (outside
Docker) across a Postgres/Valkey container restart, with an identical
match, before the Dockerized fresh-install run above superseded it as the
primary recorded result.

## Known Limitations

- MP3/M4A/WebM assets ship without `duration_ms`/`sample_rate`/`channels`/
  `codec` metadata (WAV only) — `mutagen` rejected on license grounds; no
  compliant alternative evaluated yet (ADR-0014).
- Browser/tab crash during an *active* (not-yet-stopped) recording loses
  that take — no server-side chunked capture in Phase 2 (ADR-0012).
- No per-organization/per-user storage quota — only a per-object size cap.
- No scheduled sweep of orphaned temp files or abandoned
  `RecordingUpload` sessions from a hard process crash (documented
  interim cron-based mitigation in `docs/operations/media-cleanup.md`).
- `RESTRICTED` privacy mode is modeled but doesn't yet narrow access
  beyond ordinary org+permission checks.
- No retention scheduler — `RetentionPolicy` assignment records intent
  only.
- Recording browser support was feature-detected and unit-tested but not
  exercised with a real microphone in this session (no audio input device
  in the automated browser environment) — see "Browser Recording" above.

## Open Risks

- Storage exhaustion at the aggregate (not per-object) level — acceptable
  for a single-tenant on-prem deployment where upload permission is
  operator-controlled, documented as a residual risk.
- 9 HIGH-severity Trivy findings on the backend runtime image (mostly
  Debian trixie OS packages — gzip, libacl1, ncurses, openssl — several
  marked `fix_deferred` upstream, i.e. no fix published yet by Debian at
  scan time) and 3 HIGH on the frontend build/dev image (`brace-expansion`
  in a dev-only npm dependency, never shipped). 0 HIGH on the frontend
  runtime image. **0 CRITICAL across all three images** — the CI gate
  that blocks on CRITICAL passed; HIGH findings are reported, not hidden,
  per the brief's instruction, and are the same category of "stale OS
  package snapshot" issue Phase 0 already documented as an accepted,
  monitored risk pattern.

## Architecture Deviations

- Added a minimal `GET /organizations` read-only endpoint
  (`app.organizations.router`) — not in Phase 1's scope, but required for
  the "New Conversation" org picker to be genuinely functional rather
  than hardcoded; kept intentionally small (list-only, no admin CRUD).
- Added `GET /auth/csrf` (Phase 1 identity domain) to fix a real bug: the
  frontend's in-memory CSRF token was lost on every full page reload,
  silently blocking all Phase 2 mutating actions. Re-reads (never mints)
  the token already bound to the caller's own session — see the
  endpoint's docstring and `frontend/src/auth/AuthContext.tsx`.
- Extended `StorageProvider` (`save`/`save_stream`, `namespace` param,
  `open_path`) rather than adding a parallel Phase-2-only storage
  abstraction — see ADR-0013.

## Deferred Items

- True server-side chunked recording ingestion (ADR-0012).
- MP3/M4A/WebM metadata extraction pending a compliant library evaluation
  (ADR-0014).
- Retention scheduler execution.
- RESTRICTED privacy mode's actual access-narrowing semantics.
- Per-organization/user storage quotas.
- Scheduled temp-file/abandoned-upload cleanup job.
- PWA/offline recording — briefly evaluated per the brief's request:
  **not recommended** for this product given the medical/therapy content
  sensitivity and the explicit "on-prem, no offline recording" scope note
  in the brief itself; a full PWA installability pass was not implemented.

## Git / PR / Merge Status

- Branch: `phase-2-conversation-capture`, created from `main` at `b811313`.
- PR: [#3](https://github.com/ley338-gif/VocaDox/pull/3) — squash-merged
  to `main` as commit `428cfa5`.
- Three commits on the branch: the main implementation, a ruff full-tree
  lint fix (caught by CI, not locally — documented in the commit
  message), and the Docker non-root-permission fix (caught by manual
  fresh-install testing, not CI — documented in the commit message).
- Branch deleted after merge (`gh pr merge --delete-branch`).
- No unresolved review comments (no human reviewer was available in this
  autonomous session; CI stood in as the review gate per standing policy).

## Recommendation

**GO for Phase 3.** Every gate in the standing merge-authorization
checklist passed with real, recorded evidence rather than assumption:
recordings can be created (browser flow unit-tested + consent screen
verified live; full audio pipeline verified via file upload and API),
files can be uploaded, source media is immutable and SHA-256-verified
across ingestion/download/restart, storage survives a real container
restart, authorization prevents cross-org access (hard-tested, 404 not
403), media can't be accessed anonymously, traversal attacks are
rejected, upload limits work, conversation state transitions are
controlled, deletion semantics are defined and physically enforced,
privacy/retention foundations exist (with gaps honestly documented), 128
tests pass across both stacks, CI is fully green, licenses are 0
Blocked/0 Unknown, and no unresolved Critical vulnerability exists in any
image. The known limitations above are real but scoped and documented,
not blockers to starting Phase 3's own explicit approval process.
