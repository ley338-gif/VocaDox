# 0013 — Media storage layout: namespaced opaque keys, never client paths

## Status
Accepted

## Context
Phase 0's `StorageProvider`/`LocalFilesystemStorage` (ADR-0005) already
guarantees storage keys are server-generated UUIDs, immune to path
traversal by construction. Phase 2 needs a human-navigable on-disk layout
for operators (`data/organizations/<org-id>/conversations/<conversation-id>/
{source,derived,attachments}/`) without weakening that guarantee, and
without ever using a caller-supplied filename as (part of) a path.

## Decision
`StorageProvider.save`/`save_stream` gained an optional `namespace`
parameter: a `/`-separated sequence of path *segments* that the caller
builds exclusively from values the server itself controls — organization
and conversation UUIDs (`.hex`, no dashes) and a fixed literal
(`source`/`derived`/`attachments` per `MediaKind`) — never from
`original_filename` or any other user input. Each segment is sanitized
(`_sanitize_namespace_segment`: alphanumeric, `-`, `_` only; anything that
sanitizes down to empty, e.g. a bare `..`, is rejected outright rather than
silently continuing) before being joined onto the storage root. The
returned storage key is still fully opaque from the caller's perspective —
API responses never expose it, and `media_assets.storage_key` is only ever
resolved back to a real path inside `LocalFilesystemStorage`/`app.core.
storage`.

`original_filename` is stored purely as *metadata* (for display /
`Content-Disposition`, both passed through `app.media.validation.
sanitize_display_filename` / `content_disposition_filename`) and never
touches the storage key at all —
`tests/media/test_service.py::test_ingest_media_never_reuses_a_client_supplied_path`
asserts this directly with a `../../../etc/passwd`-style filename.

## Alternatives considered
- **Flat root, no namespace (Phase 0's original shape).** Rejected only
  because it makes the filesystem unreadable to an operator trying to
  reason about disk usage per organization/conversation during an
  incident — functionally it was already safe.
- **Namespace built from `organization.slug`/`conversation.title`.**
  Rejected — those are user-influenced strings (an org name or
  conversation title could contain `..`, be renamed, or collide after
  sanitization), reintroducing exactly the risk UUID-only keys eliminate.

## Consequences
- Two different `MediaAsset`s always get two different storage keys even
  if uploaded with the same original filename (the UUID filename component
  guarantees this) — no path collision handling needed.
- An operator can `du -sh data/organizations/<org-id>` to see one
  organization's on-disk footprint without querying the database first.
