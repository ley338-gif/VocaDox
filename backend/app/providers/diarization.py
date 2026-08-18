"""Speaker diarization provider abstraction.

`DiarizationResult` is the one internal normalized contract (spec:
"Diarization normalized result") — provider-specific speaker labels are
normalized into generic `SPEAKER_00`-style labels here; nothing
provider-specific leaks past this boundary. Overlapping speech is
represented honestly (multiple turns may cover the same time range) —
never collapsed into a false single-speaker-at-a-time guarantee.

`PyannoteDiarizationProvider` (real, local — see
docs/architecture/adr/0017-diarization-provider-selection.md for the full
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
from typing import Any


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
    # Shared Hugging Face cache holding the pipeline's dependent sub-models
    # (segmentation, speaker embedding — see app.cli.install_models'
    # DependentRepo docstring for why these are separate downloads).
    # `None` disables offline-forced loading entirely (only used by tests
    # that never construct a real pipeline).
    hf_cache_dir: str | None = None


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

    def _ensure_loaded(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        if not self._is_installed():
            raise DiarizationModelUnavailableError(
                f"diarization model not installed at {self._config.model_dir} — run "
                "`docker compose run --rm model-manager install diarization-default` "
                "(see docs/admin/model-installation.md)"
            )
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:  # pragma: no cover
            raise DiarizationModelUnavailableError(
                "pyannote.audio is not installed in this environment"
            ) from exc

        # The pipeline's config.yaml names two further Hugging Face repos by
        # id (segmentation, speaker embedding — see
        # app.cli.install_models.DependentRepo) that pyannote.audio resolves
        # internally via huggingface_hub, not from `model_dir` itself.
        # `hf_cache_dir` points it at the shared local cache those repos
        # were installed into; whether it's actually forced offline (so a
        # missing dependent repo fails clearly instead of silently reaching
        # the network) is decided once, process-wide, by
        # `app.workers._offline_env` at worker startup — NOT here.
        # `HF_HUB_OFFLINE` cannot be toggled per-call: huggingface_hub reads
        # it from `os.environ` exactly once, at that module's own first
        # import, and caches it as a plain bool forever after — a real
        # fresh-install test found this the hard way when an earlier
        # version of this fix set the env var right here, immediately
        # before this call, and it silently did nothing (huggingface_hub
        # was already imported by this point in the process).
        try:
            pipeline = Pipeline.from_pretrained(
                self._config.model_dir, cache_dir=self._config.hf_cache_dir
            )
        except Exception as exc:  # noqa: BLE001
            raise DiarizationModelUnavailableError(
                f"failed to load diarization model: {exc}"
            ) from exc

        if pipeline is None:
            raise DiarizationModelUnavailableError(
                "failed to load diarization model: Pipeline.from_pretrained returned None "
                "(a dependent sub-model is likely missing from the local Hugging Face cache — "
                "re-run `docker compose run --rm model-manager install diarization-default`)"
            )
        device = self._resolved_device()
        if device == "cuda":
            import torch

            pipeline.to(torch.device("cuda"))
        self._pipeline = pipeline
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
