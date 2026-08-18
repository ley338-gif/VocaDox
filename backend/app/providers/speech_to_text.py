"""Speech-to-text provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A single transcribed span. Mirrors the eventual transcript_segments table shape."""

    start_seconds: float
    end_seconds: float
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str


class SpeechToTextProvider(ABC):
    """Real implementations (Whisper, ...) land in Phase 3. Interface only here."""

    @abstractmethod
    async def transcribe(
        self, media_path: str, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        raise NotImplementedError


class FakeSpeechProvider(SpeechToTextProvider):
    """Deterministic synthetic transcription for tests and local dev."""

    async def transcribe(
        self, media_path: str, *, language_hint: str | None = None
    ) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[
                TranscriptSegment(0.0, 2.5, "This is a fake transcript segment.", 0.99),
                TranscriptSegment(2.5, 5.0, "Generated deterministically for tests.", 0.98),
            ],
            language=language_hint or "en",
        )
