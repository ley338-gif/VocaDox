# Changelog

All notable changes to VocaDox are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and released
versions follow Semantic Versioning.

## [Unreleased]

Target version: `0.14.0` (first coordinated pre-1.0 release). It will receive
a release date and Git tag only if the Phase 14 validation report recommends
release.

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
