"""Media normalization abstraction, decoupled from any concrete tool.

No FFmpeg (or any other transcoding engine) is introduced in Phase 2. The
brief's instruction is explicit: if a normalization tool is ever adopted,
STOP and evaluate its exact build/license/codec configuration first (never
assume "FFmpeg = LGPL" — the effective license depends on which codecs are
compiled in) and write a dedicated ADR. That evaluation has not happened,
so Phase 2 ships only `NoOpMediaNormalizer`, which is correct for the
formats Phase 2 actually accepts (see app.media.validation) — they are
already directly playable in-browser without transcoding. Real
transcoding-based normalization is deferred to a later phase's ADR.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationInput:
    data: bytes
    content_type: str
    container: str | None


@dataclass(frozen=True)
class NormalizationResult:
    data: bytes
    content_type: str
    container: str | None
    codec: str | None


class MediaNormalizer(ABC):
    @abstractmethod
    async def normalize(self, source: NormalizationInput) -> NormalizationResult:
        """Produce derived media from `source`. Must never mutate or
        depend on being able to mutate the original source bytes/row —
        callers persist the result as a brand new MediaAsset."""
        raise NotImplementedError


class NoOpMediaNormalizer(MediaNormalizer):
    """Passes already-compatible input through unchanged. Correct for
    Phase 2's supported format set (WebM/Opus, WAV, MP3, M4A), which the
    frontend audio player already handles natively — no transcoding step
    is actually needed yet."""

    async def normalize(self, source: NormalizationInput) -> NormalizationResult:
        return NormalizationResult(
            data=source.data,
            content_type=source.content_type,
            container=source.container,
            codec=None,
        )
