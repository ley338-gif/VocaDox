# Media security (Phase 2)

Extends `docs/security/threat-model.md` §7 with the operational
verification performed for the Phase 2 validation report.

## Source integrity (SHA-256)

Every ingested `MediaAsset` gets a SHA-256 computed once, while bytes are
first spooled (`app.media.service.spool_upload`), and persisted in
`media_assets.sha256`. It is never recomputed or overwritten afterward.

Verification performed against the real Docker-composed Postgres +
filesystem storage (not the SQLite test fixtures) for the Phase 2
validation report: SHA-256 of a synthetic WAV, computed client-side before
ingestion, was compared against the stored `media_assets.sha256`
immediately after ingestion, then again after restarting the Postgres and
Valkey containers and re-reading the file from disk. All three values
matched — see `PHASE_2_VALIDATION_REPORT.md`, "Source Integrity
Validation" for the exact recorded result.

## Path traversal & filename injection

`LocalFilesystemStorage` keys are always server-generated (UUID +
sanitized namespace segments); `original_filename` never touches a
storage path. Tested explicitly against `../../etc/passwd`, absolute
paths, encoded traversal (`..%2f..%2f...`), and CRLF-header-injection
filenames — see `tests/test_providers.py`,
`tests/media/test_validation.py`, and
`tests/conversations/test_api.py::
test_malicious_filename_does_not_leak_into_storage_or_headers`.

## Unauthorized media access

The storage directory is never served directly by nginx or any static
file mechanism — `docker-compose`'s frontend container serves only the
built SPA, and the backend is the sole path to any media byte, gated by
`app.conversations.authz.authorize_conversation_access` on every request.

## Cross-organization isolation

Treated as a hard security property, tested heavily (not a nice-to-have):
`tests/conversations/test_api.py::
test_cross_organization_uuid_guessing_is_denied`,
`::test_media_access_denied_across_organizations`,
`::test_system_admin_can_access_any_organization_conversation`,
`::test_missing_permission_is_denied`,
`::test_unauthenticated_request_is_denied`. Denied access always returns
`404` (never `403`) for "wrong organization," so the response itself
cannot be used to enumerate other organizations' conversation IDs.

## Malicious/malformed media

Magic-byte sniffing (`app.media.validation.sniff_audio_format`) rejects
anything that isn't a recognized audio container, including HTML/SVG/
script content wrapped in an audio-sounding filename or
`Content-Type` — the media endpoint never executes or renders uploaded
content as anything but opaque audio bytes served with the format's own
`Content-Type`.

## Resource limits

`Settings.max_upload_size_bytes` (default 2 GiB) is enforced while
streaming, before the full payload is buffered — see
`app.media.service.spool_upload`. No per-organization/per-user aggregate
quota exists yet (see threat-model.md §7, "Storage exhaustion").

## Residual risks (not resolved in Phase 2)

- No storage-exhaustion quota beyond the per-upload size cap.
- No scheduled sweep of orphaned temp files from a hard process crash
  (see `docs/operations/media-cleanup.md`).
- MP3/M4A/WebM metadata fields are unpopulated (functional limitation,
  not a security one — see ADR-0014).

These are documented as open items in `PHASE_2_VALIDATION_REPORT.md`
rather than silently accepted.
