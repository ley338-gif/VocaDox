"""Audio metadata extraction: duration/codec/container/sample rate/channels,
extracted "where reliably possible" per the Phase 2 brief.

WAV only, via the stdlib `wave` module — no third-party dependency.

A pure-Python metadata library (`mutagen`) was evaluated as a candidate for
extending this to MP3/M4A/WebM and REJECTED: its actual PyPI-declared
license is GPL-2.0-or-later (verified against the live PyPI JSON API,
https://pypi.org/pypi/mutagen/json, 2026-08-18 — not assumed from memory),
which falls in the `blocked` bucket of compliance/license-policy.yml. No
compliant alternative was identified within Phase 2's scope, so MP3/M4A/
WebM assets are ingested and playable but ship with `duration_ms` /
`sample_rate` / `channels` / `codec` left `None`. This is a documented,
honest known limitation (see docs/architecture/media-ingestion.md), not a
silently-missing feature — evaluating a compliant metadata library for
these formats is deferred to a later phase.

Failure is non-fatal: if metadata can't be reliably determined (corrupt/
unusual file), every field is simply left None rather than raising —
ingestion should not fail just because we couldn't read optional metadata.
"""

from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioMetadata:
    duration_ms: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None


def extract_audio_metadata(data: bytes, *, container: str) -> AudioMetadata:
    if container != "wav":
        # MP3/M4A/WebM: no compliant metadata library adopted yet (see
        # module docstring) — every field stays None rather than guessing.
        return AudioMetadata()
    try:
        return _extract_wav(data)
    except Exception:  # noqa: BLE001 - metadata extraction must never fail ingestion
        return AudioMetadata()


def _extract_wav(data: bytes) -> AudioMetadata:
    import wave

    with wave.open(io.BytesIO(data), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        duration_ms = int(round((frames / rate) * 1000)) if rate else None
        return AudioMetadata(
            duration_ms=duration_ms, sample_rate=rate, channels=channels, codec="pcm"
        )
