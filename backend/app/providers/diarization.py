"""Speaker diarization provider abstraction.

`DiarizationResult` is the one internal normalized contract (spec:
"Diarization normalized result") — provider-specific speaker labels are
normalized into generic `SPEAKER_00`-style labels here; nothing
provider-specific leaks past this boundary. Overlapping speech is
represented honestly (multiple turns may cover the same time range) —
never collapsed into a false single-speaker-at-a-time guarantee.

`PyannoteDiarizationProvider` (real, local — see
docs/architecture/adr/0015-diarization-provider-selection.md for the full
license/evaluation) is the Phase 3 production provider. The
`pyannote/speaker-diarization-3.1` pipeline is MIT-licensed but *gated* on
Hugging Face (requires accepting terms + an access token to download) —
VocaDox never bundles or silently downloads it; an admin installs it
explicitly (docs/admin/model-installation.md). `FakeDiarizationProvider`
remains what CI/unit tests/GPU-less dev use exclusively.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class DiarizationModelUnavailableError(RuntimeError):
    """Raised when the configured diarization model/pipeline is not
    installed/loadable. Callers must classify the resulting job failure as
    MODEL_UNAVAILABLE."""


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    start_seconds: float
    end_seconds: float
    speaker_label: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    turns: list[SpeakerTurn]
    speaker_count: int


@dataclass(frozen=True, slots=True)
class DiarizationProviderStatus:
    provider: str
    model: str
    model_revision: str | None
    installed: bool
    detail: str | None = None


class DiarizationProvider(ABC):
    """Real implementations (pyannote, ...) land in Phase 3/4. Interface only here."""

    @abstractmethod
    async def diarize(
        self,
        media_path: str,
        *,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> DiarizationProviderStatus:
        raise NotImplementedError


class FakeDiarizationProvider(DiarizationProvider):
    """Deterministic synthetic diarization for tests and local dev."""

    async def diarize(
        self,
        media_path: str,
        *,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult:
        return DiarizationResult(
            turns=[
                SpeakerTurn(0.0, 2.5, "SPEAKER_00", 0.95),
                SpeakerTurn(2.5, 5.0, "SPEAKER_01", 0.93),
            ],
            speaker_count=2,
        )

    def status(self) -> DiarizationProviderStatus:
        return DiarizationProviderStatus(
            provider="fake",
            model="fake-deterministic",
            model_revision=None,
            installed=True,
            detail="Deterministic fake provider for tests/dev — never used in production.",
        )


@dataclass(frozen=True, slots=True)
class PyannoteConfig:
    model_dir: str  # local path under the persistent model volume (post-download snapshot)
    model_name: str = "pyannote/speaker-diarization-3.1"
    model_revision: str = "84fd25912480287da0247647c3d2b4853cb3ee5"
    device: str = "auto"


class PyannoteDiarizationProvider(DiarizationProvider):
    """Real local diarization via pyannote.audio's pretrained pipeline,
    loaded from a locally-installed snapshot (never downloaded from
    Hugging Face at request time in production — see
    docs/admin/model-installation.md)."""

    def __init__(self, config: PyannoteConfig) -> None:
        self._config = config
        self._pipeline = None

    def _is_installed(self) -> bool:
        from pathlib import Path

        path = Path(self._config.model_dir)
        return path.exists() and any(path.iterdir()) if path.exists() else False

    def _resolved_device(self) -> str:
        from app.providers.device import select_device

        if self._config.device == "auto":
            return select_device(prefer_gpu=True)
        return self._config.device

    def _ensure_loaded(self):  # noqa: ANN202
        if self._pipeline is not None:
            return self._pipeline
        if not self._is_installed():
            raise DiarizationModelUnavailableError(
                f"diarization model not installed at {self._config.model_dir} — run "
                "`vocadox models install diarization-default` "
                "(see docs/admin/model-installation.md)"
            )
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:  # pragma: no cover
            raise DiarizationModelUnavailableError(
                "pyannote.audio is not installed in this environment"
            ) from exc

        try:
            pipeline = Pipeline.from_pretrained(self._config.model_dir)
            device = self._resolved_device()
            if device == "cuda":
                pipeline.to(torch.device("cuda"))
            self._pipeline = pipeline
        except Exception as exc:  # noqa: BLE001
            raise DiarizationModelUnavailableError(
                f"failed to load diarization model: {exc}"
            ) from exc
        return self._pipeline

    async def diarize(
        self,
        media_path: str,
        *,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult:
        import asyncio

        def _run() -> DiarizationResult:
            pipeline = self._ensure_loaded()
            kwargs: dict[str, int] = {}
            if min_speakers is not None:
                kwargs["min_speakers"] = min_speakers
            if max_speakers is not None:
                kwargs["max_speakers"] = max_speakers
            diarization = pipeline(media_path, **kwargs)

            turns: list[SpeakerTurn] = []
            labels: set[str] = set()
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                labels.add(speaker)
                turns.append(
                    SpeakerTurn(
                        start_seconds=turn.start,
                        end_seconds=turn.end,
                        speaker_label=speaker,
                        confidence=1.0,  # pyannote's default pipeline does not expose
                        # a per-turn confidence score; documented as an honest 1.0
                        # placeholder rather than a fabricated calibrated value.
                    )
                )
            return DiarizationResult(turns=turns, speaker_count=len(labels))

        return await asyncio.to_thread(_run)

    def status(self) -> DiarizationProviderStatus:
        installed = self._is_installed()
        return DiarizationProviderStatus(
            provider="pyannote.audio",
            model=self._config.model_name,
            model_revision=self._config.model_revision,
            installed=installed,
            detail=None if installed else "model not installed at configured model_dir",
        )
