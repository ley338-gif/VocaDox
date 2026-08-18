# 0019 — Media normalization via a real transcoding engine (FFmpeg, LGPL build)

## Status
Accepted

## Context
Phase 2 (ADR-0014, "media normalization and metadata") deliberately shipped
only `NoOpMediaNormalizer`, explicitly deferring any real transcoding
engine until its exact build/license/codec configuration could be
evaluated — never assume "FFmpeg = LGPL," since the effective license
depends on which codecs are compiled in. Phase 3's speech/diarization
providers need a specific input format, so that evaluation now happens.

## Target format
Verified (not assumed) against both providers:
- faster-whisper's own README states Whisper models "are trained... to
  operate on audio sampled at 16kHz."
- pyannote.audio's pipelines resample any input to 16 kHz mono internally
  regardless of what they're given.

Decision: normalize to **mono, 16 kHz, 16-bit PCM WAV** (`pcm_s16le`).
This is a single unambiguous format both providers accept directly,
avoids relying on either provider's own internal resampling behavior, and
keeps derived-asset size small and predictable.

## FFmpeg build/license audit
Debian's own `ffmpeg` package (what `apt-get install ffmpeg` on the
`python:3.11-slim-trixie` base image would install) is built with
`--enable-gpl` (confirmed via Debian's own package build log/search) —
**not acceptable** for a closed, commercially-deployed product image
under this project's license policy (GPL is in the `blocked` bucket of
`compliance/license-policy.yml`).

Instead, `backend/worker.Dockerfile` downloads a **statically-built,
LGPL-only-configured** FFmpeg from BtbN/FFmpeg-Builds
(`https://github.com/BtbN/FFmpeg-Builds`, itself MIT-licensed build
tooling — the *ffmpeg binary it produces* carries ffmpeg's own license):

- Downloaded and inspected 2026-08-18: `ffmpeg-master-latest-linux64-lgpl.tar.xz`,
  sha256 `079be6e766720bf2b1e1d71073214a51cae831295cbcc92e64d31e422fcb5ec1`
  (114,463,920 bytes), version string
  `N-126188-g426841da9d-20260817`.
- `LICENSE.txt` inside the archive is the **GNU Lesser General Public
  License v3**.
- `ffmpeg -version`'s printed `configuration:` string was inspected
  directly (run inside a `debian:trixie-slim` container, not assumed):
  **no** `--enable-gpl`, **no** `--enable-nonfree`; `--disable-libx264
  --disable-libx265 --disable-libxavs2 --disable-libxvid` are present
  (the GPL-licensed codecs are explicitly compiled out). `--enable-version3`
  is present (LGPLv3 terms), matching `LICENSE.txt`.
- `--enable-libmp3lame` is present — libmp3lame (LAME) is itself LGPL,
  consistent with an LGPL-only build; VocaDox only *decodes* MP3 input
  (never encodes it), so this is moot for our actual usage but confirms
  the build genuinely excludes GPL components rather than merely omitting
  the `--enable-gpl` flag while still linking GPL code.

`backend/worker.Dockerfile` downloads this exact archive and verifies its
sha256 before extracting — since BtbN publishes a continuously-updated
rolling `latest` release tag (not a fixed version tag), the Dockerfile
pins by **content hash**, not by tag: if upstream ever republishes
different bytes under the same tag, the build fails closed (checksum
mismatch) rather than silently accepting a different, unaudited binary.
Re-pinning to a newer hash is a deliberate, reviewed Dockerfile change.

## Implementation
`app/media/normalizer.FfmpegMediaNormalizer`: invokes `ffmpeg` via
`asyncio.create_subprocess_exec` with a fixed, safe argument list (never
shell interpolation), a configurable subprocess timeout
(`Settings.normalization_subprocess_timeout_seconds`, default 600s), an
input size cap, and controlled temp paths that are always cleaned up
(`finally: shutil.rmtree`). Selected automatically at DI time
(`app/core/ai_providers.get_media_normalizer`) only when an `ffmpeg`
binary is resolvable on `PATH`; falls back to the Phase 2
`NoOpMediaNormalizer` otherwise (documented degradation, not a crash) —
this means the `api`/CI images (which never install ffmpeg) safely no-op,
while only the worker images (which do install the audited LGPL build)
perform real transcoding.

## Consequences
- Original `SourceMedia` is never touched — normalization always produces
  a new `MediaAsset` (`kind=NORMALIZED_AUDIO`), matching ADR-0011's
  immutable-source rule.
- Idempotency: normalization output is keyed on `source_media_id +
  normalizer_version + normalization_profile` (see
  `app/processing/orchestrator.NORMALIZER_VERSION`) so a retried
  NORMALIZE job reuses a prior successful output instead of duplicating
  it.
- `compliance/container-inventory.yml`/dependency notes record the FFmpeg
  binary as a pinned-by-hash download inside `worker.Dockerfile`, not a
  PyPI/npm package, and its license (LGPL-3.0) is tracked as
  `review_required` per `compliance/license-policy.yml` with the audit
  above as its sign-off note (unmodified LGPL dynamic dependency, no
  static-linking/redistribution obligation conflict for an on-premise
  deployment).
