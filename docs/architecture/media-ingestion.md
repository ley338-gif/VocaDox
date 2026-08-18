# Media ingestion (Phase 2)

## Two paths, one architecture

Both "record now" (browser `MediaRecorder`, finalized via
`POST /conversations/{id}/recordings`) and "upload audio" (existing file,
via `POST /conversations/{id}/media`) converge on the same
`app.media.service.ingest_media` function and produce the same
`MediaAsset` shape — no separate processing systems, matching the brief's
requirement directly.

## Pipeline

1. **Spool** (`spool_upload`): stream request bytes to a controlled temp
   file, computing SHA-256 and enforcing `max_upload_size_bytes` as data
   arrives — never buffers the whole payload in memory first. Rejects
   empty uploads outright.
2. **Sniff** (`app.media.validation.sniff_audio_format`): magic-byte
   inspection against the supported-format allow-list (WebM/Opus, WAV,
   MP3, M4A) — the declared `Content-Type` is never trusted alone.
   Anything else (including HTML/SVG dressed up with an audio filename) is
   rejected with `422`.
3. **Extract metadata** (`app.media.metadata.extract_audio_metadata`):
   WAV only, via the stdlib `wave` module. See "Known limitation" below.
4. **Persist**: create the `MediaAsset` row, then atomically move the temp
   file into permanent storage under the conceptual
   `organizations/<org>/conversations/<conv>/{source,derived,attachments}/`
   layout (opaque key — see `docs/architecture/media-storage.md`).

## Supported audio formats (exactly what's tested)

| Format | Container | Detection | Notes |
|---|---|---|---|
| WebM/Opus | `webm` | EBML magic bytes | Default browser `MediaRecorder` output |
| WAV | `wav` | `RIFF...WAVE` header | Full metadata extraction (stdlib `wave`) |
| MP3 | `mp3` | `ID3` tag or bare MPEG frame sync | No metadata extraction (see below) |
| M4A/AAC | `m4a` | ISO-BMFF `ftyp` + brand | No metadata extraction (see below) |

Nothing else is accepted. This list is deliberately small — see
`app/media/validation.py`'s module docstring.

## Known limitation: metadata extraction

Only WAV gets real `duration_ms`/`sample_rate`/`channels`/`codec`. MP3/
M4A/WebM assets ingest, hash, store, and play correctly, but ship with
those four fields `None`. This is because the evaluated candidate library
(`mutagen`) turned out to be GPL-2.0-or-later — blocked by
`compliance/license-policy.yml` — not because it was skipped; see
[ADR-0014](adr/0014-media-normalization-and-metadata.md) for the full
investigation. The audio player itself is unaffected: it reads
duration/position from the browser's own decode of the file, not from
this backend-stored metadata.

## Normalization

`app.media.normalizer.MediaNormalizer` is the abstraction; Phase 2 only
ships `NoOpMediaNormalizer` (input already directly playable, no
transcoding needed for the supported format set). No FFmpeg or other tool
is invoked anywhere in Phase 2 — see ADR-0014.

## Idempotent recording finalize

`POST /conversations/{id}/recordings?idempotency_key=...` is safe to retry
with the same key: a `RecordingUpload` row tracks `(conversation_id,
idempotency_key) → status/result_media_id`, and a repeated finalize with a
`COMPLETED` row returns the existing `MediaAsset` instead of creating a
duplicate. See [ADR-0012](adr/0012-chunked-upload-decision.md) for why
this is upload-once rather than server-side chunked ingestion.
