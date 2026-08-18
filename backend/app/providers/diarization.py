"""Speaker diarization provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    start_seconds: float
    end_seconds: float
    speaker_label: str


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    turns: list[SpeakerTurn]
    speaker_count: int


class DiarizationProvider(ABC):
    """Real implementations (pyannote, ...) land in Phase 3/4. Interface only here."""

    @abstractmethod
    async def diarize(self, media_path: str) -> DiarizationResult:
        raise NotImplementedError


class FakeDiarizationProvider(DiarizationProvider):
    """Deterministic synthetic diarization for tests and local dev."""

    async def diarize(self, media_path: str) -> DiarizationResult:
        return DiarizationResult(
            turns=[
                SpeakerTurn(0.0, 2.5, "speaker_1"),
                SpeakerTurn(2.5, 5.0, "speaker_2"),
            ],
            speaker_count=2,
        )
