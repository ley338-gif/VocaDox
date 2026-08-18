# Media storage (Phase 2)

## Storage provider

Extends the Phase 0 `StorageProvider`/`LocalFilesystemStorage`
architecture (`backend/app/providers/storage.py`) — Phase 2 does not
bypass or reimplement it. Two additions:

- **`namespace` parameter** on `save`/`save_stream`: server-controlled
  path segments (organization/conversation UUID hex + a fixed
  `source`/`derived`/`attachments` literal) giving the on-disk layout
  `data/organizations/<org-id>/conversations/<conversation-id>/
  {source,derived,attachments}/<uuid>.<ext>` without weakening the
  path-traversal guarantee — see
  [ADR-0013](adr/0013-media-storage-layout.md).
- **`save_stream`/`open_path`**: streams a spooled temp file into
  permanent storage via `Path.replace` (atomic rename, same filesystem)
  with a blocking-copy fallback across filesystems, and exposes a real
  path for range-request-capable serving — never a public path, only used
  internally by `FileResponse` in the media-content endpoint.

Storage root is `Settings.media_storage_root`
(`VOCADOX_MEDIA_STORAGE_ROOT`, default `./data/media`) — configurable, no
hardcoded paths anywhere in domain code (enforced by architecture-boundary
convention; `LocalFilesystemStorage` itself is only ever constructed via
`app.core.storage.get_storage_provider`, never imported directly by a
domain package — see `tests/test_architecture_boundaries.py`).

## Opaque keys

`media_assets.storage_key` is never exposed by any API response. Public
endpoints only ever expose the `media_assets.id` (a UUID unrelated to the
storage key); the content is served via
`GET /conversations/{id}/media/{media_id}/content`, which resolves the
storage key to a real path server-side after authorization.

## Serving media

`GET .../content` uses Starlette's `FileResponse`, which supports HTTP
Range requests natively — verified manually against a real audio file
(range-request support is a Starlette/ASGI-server property, not something
Phase 2 hand-rolled). `Content-Disposition`'s filename is built from
`app.media.validation.content_disposition_filename` — ASCII-only, no raw
quotes/backslashes, and (upstream of that) CR/LF already stripped by
`sanitize_display_filename`, so a malicious original filename can't inject
response headers.

## Temp files

`Settings.upload_temp_dir` (`VOCADOX_UPLOAD_TEMP_DIR`, default
`./data/tmp-uploads`) is a controlled directory; `spool_upload`
(`app.media.service`) writes with `tempfile.mkstemp` (unpredictable name)
and `0o600` permissions where the OS supports it, and deletes the temp
file on any validation or ingestion failure. See
`docs/operations/media-cleanup.md` for the operational sweep strategy for
anything a hard crash leaves behind.

## Consistency model (filesystem + Postgres)

See [ADR-0011](adr/0011-source-media-separation.md) and
`app.media.service`'s module docstring for the full sequence: spool →
validate/hash → DB insert (flush, not committed) → atomic move into
storage → commit. A crash between the atomic move and the commit can
leave an orphaned file on disk (never an orphaned DB row referencing
missing storage) — acceptable, addressed operationally rather than with
distributed-transaction machinery Phase 2's scope doesn't justify.
