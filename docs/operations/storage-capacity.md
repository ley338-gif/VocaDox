# Operations: storage capacity

## Sizing

Phase 2 targets recordings up to 120+ minutes. A rough sizing guide for
uncompressed/lightly-compressed audio:

| Format | Approx. size per hour (mono, speech-quality) |
|---|---|
| WAV (16-bit, 16kHz) | ~115 MB |
| WebM/Opus (default browser recording, ~32-64kbps) | ~15-30 MB |
| MP3 (128kbps) | ~55 MB |

Plan `media_storage_root`'s filesystem capacity around your expected
conversation volume × average duration × format mix. There is no
automatic compression/normalization changing a source file's size in
Phase 2 (`NoOpMediaNormalizer` — see
[ADR-0014](../architecture/adr/0014-media-normalization-and-metadata.md)).

## No quota enforcement

Phase 2 enforces a per-object size cap (`max_upload_size_bytes`) but no
aggregate quota per organization or user. Monitor disk usage directly; the
namespaced storage layout
(`data/organizations/<org-id>/conversations/<conversation-id>/...`) makes
per-organization `du` straightforward. Alert on the underlying filesystem
approaching capacity the same way you would for Postgres's data volume.

## Growth over time

Because source media is immutable and derived media is always a separate
object (see ADR-0011), storage usage only grows as normalization/future
phases add derived assets — plan capacity assuming source media size is a
floor, not a ceiling, once real transcoding-based normalization ships.
