# Changelog

All notable changes to VocaDox are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and released
versions follow Semantic Versioning.

## [Unreleased]

Target version: `0.14.0` (first coordinated pre-1.0 release). It will receive
a release date and Git tag only if the Phase 14 validation report recommends
release.

### Added

- **R0 (research roadmap, post-GA)**: local, provider-agnostic diarization
  accuracy evaluation framework (DER/JER, pure stdlib) wired into the
  Evaluation Lab as a new `diarization_accuracy` run type
  (`POST /admin/evaluation/diarization-accuracy`, new "Sprechererkennung
  (DER/JER)" Admin UI tab) — the test-infrastructure fix for Phase 12
  Finding #12 ("genuine multi-voice diarization accuracy has never been
  empirically verified"). Includes a dev-only FastMSS integration
  (`tools/dev/fastmss/`, GPL-3.0, never installed/vendored/shipped — see
  `compliance/exceptions.yml`) for generating real, genuinely-distinct-
  voice fixtures at three overlap levels. See
  `PHASE_R0_VALIDATION_REPORT.md` and ADR-0047.

- Conversation participants can now be added from the organization's
  registered-user directory, not just as free-text names or existing Known
  Speakers. The link (`conversation_participants.user_id`) is persisted
  independently of the existing `known_speaker_id` link, enabling future
  "I was there" attribution/avatar display, while `display_name` remains a
  free-text label that is never required to be a real name. New endpoint:
  `GET /organizations/{id}/member-users`, gated by a new `user:read-directory`
  permission (granted to the Manager and User roles). Upgrading an existing
  installation requires `alembic upgrade head` followed by
  `python -m app.identity.seed` — see `docs/admin/admin-portal.md`.

### Changed

- Began Phase 14 production-readiness work.
- Reconciled visible project status and version metadata with the current
  repository state.
- Added committed Python lockfiles for the backend and GDT bridge, made CI
  and container builds consume locked dependency trees, and removed npm's
  permissive install fallbacks.
- Pinned the frontend build-tool versions and applied current Alpine security
  package revisions in both frontend image stages.

### Security

- A complete Phase 13+ security and privacy review is pending. Until it and
  the remaining Phase 14 release gates are complete, the repository does not
  claim a supported production release.
