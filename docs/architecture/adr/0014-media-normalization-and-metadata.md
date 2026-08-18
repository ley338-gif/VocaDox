# 0014 — Media normalization stays a NoOp; mutagen rejected for metadata

## Status
Accepted

## Context
The brief requires the *architecture* for media normalization
(`MediaNormalizer.normalize(source) -> derived`) to exist, decoupled from
any concrete tool, and is explicit that adopting a real transcoding engine
(FFmpeg or otherwise) requires stopping to evaluate its exact build/license/
codec configuration first — "FFmpeg = LGPL" is not a safe assumption, the
effective license depends on which codecs are compiled in.

Separately, the brief asks for duration/codec/sample-rate/channel
extraction "using a well-maintained permissively-licensed library rather
than hand-parsing formats."

## Decision
**Normalization**: Phase 2 ships only `NoOpMediaNormalizer`
(`app/media/normalizer.py`), which passes already-compatible input through
unchanged. This is correct, not a placeholder cop-out: Phase 2's supported
format set (WebM/Opus, WAV, MP3, M4A — see
`app/media/validation.py`) is already directly playable by the frontend's
`<audio>`-element-based player without transcoding. No FFmpeg (or any other
tool) evaluation has been done, so none is used; if a later phase needs
real transcoding, it gets its own ADR with the full build/codec/license
investigation the brief requires.

**Metadata extraction**: `mutagen` was evaluated as the candidate library
for MP3/M4A/WebM duration/codec/sample-rate extraction and **rejected**.
A live lookup against the PyPI JSON API
(`https://pypi.org/pypi/mutagen/json`, 2026-08-18) returned
`license_expression: GPL-2.0-or-later` — squarely in the `blocked` bucket
of `compliance/license-policy.yml`. The initial assumption that a
pure-Python metadata library would be permissively licensed was wrong, and
the license gate caught it before any dependency was actually shipped
(`pyproject.toml` briefly listed it, then was reverted in the same PR —
see git history — never merged to `main`). No compliant alternative was
identified within Phase 2's time budget, so:

- **WAV** metadata (duration/sample rate/channels) is extracted via the
  stdlib `wave` module — no third-party dependency, no license question.
- **MP3/M4A/WebM** assets are ingested, hashed, stored, and playable, but
  ship with `duration_ms`/`sample_rate`/`channels`/`codec` left `None`.
  This is a real, documented gap (see `docs/architecture/media-ingestion.md`,
  "Known limitation: metadata extraction"), not silently missing data —
  the frontend `<audio>` player still reports duration/current time
  correctly by reading it directly from the browser-decoded file, since
  that doesn't depend on the backend's stored metadata at all.

## Alternatives considered
- **Hand-rolling MP3/M4A/WebM metadata parsers.** Rejected for Phase 2's
  time budget — three container formats' worth of hand-parsing is real
  effort for a non-essential field, and the brief explicitly prefers a
  well-maintained library over hand-parsing when one is actually
  available and compliant.
- **Other pure-Python audio metadata libraries** (e.g. `tinytag`,
  `audio-metadata`). Not evaluated in Phase 2 — flagged as a good
  starting point for whoever picks this back up (see Deferred Items in
  `PHASE_2_VALIDATION_REPORT.md`), provided the same live-PyPI-lookup
  discipline is applied rather than assuming a license from memory.

## Consequences
- Conversation list/detail views cannot show a reliable duration for
  MP3/M4A/WebM-sourced media from backend metadata alone (WAV works
  today); the audio player itself still shows correct duration/position
  once the file is loaded client-side.
- `compliance/dependency-inventory.yml`'s direct-dependency count is
  unchanged from Phase 1 — no new runtime dependency was added in Phase 2.
