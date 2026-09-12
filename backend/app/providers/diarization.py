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

`SortformerDiarizationProvider` (R1, research roadmap, post-GA — see
docs/architecture/adr/0048-sortformer-second-diarization-provider.md) is a
SECOND, genuinely independent `DiarizationProvider` implementation, added
so R0's DER/JER eval framework has more than one real provider to compare
pyannote against (Phase 12 GA validation Finding #12). It wraps NVIDIA
NeMo's `nvidia/diar_streaming_sortformer_4spk-v2` (CC BY 4.0, not gated —
verified directly against the Hugging Face model API, see the ADR) the
same way `PyannoteDiarizationProvider` wraps pyannote: a locally-installed
`.nemo` checkpoint, loaded fully offline via NeMo's own
`restore_from()` API (never downloaded at request time), never assumed
installed. **Real NeMo inference was NOT executed in R1's own development
sandbox** (no GPU, no `nemo_toolkit` install, no model download available
there) — this implementation follows NeMo's documented model-card usage
pattern faithfully but is honestly unverified end-to-end; see
PHASE_R1_VALIDATION_REPORT.md.
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
    # Per-speaker-label voice embedding vector (post-GA P1-2 voiceprint
    # enrollment), when the provider exposes one. `None` for providers
    # that don't compute embeddings; individual labels may also be absent
    # from the dict if extraction failed for just that speaker.
    speaker_embeddings: dict[str, list[float]] | None = None


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
            # Fixed, deterministic, clearly-distinguishable stand-in vectors
            # so voiceprint-matching tests never depend on real acoustics.
            speaker_embeddings={
                "SPEAKER_00": [1.0, 0.0, 0.0, 0.0],
                "SPEAKER_01": [0.0, 1.0, 0.0, 0.0],
            },
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
            output = pipeline(media_path, **kwargs)
            # pyannote.audio 4.x's SpeakerDiarization pipeline returns a
            # `DiarizeOutput` dataclass (speaker_diarization /
            # exclusive_speaker_diarization / speaker_embeddings), not the
            # bare `pyannote.core.Annotation` earlier pyannote versions
            # returned directly — found by real diarization inference
            # testing (a mock/fake-provider-only test suite could never
            # have caught this: `FakeDiarizationProvider` never calls the
            # real library at all). `speaker_diarization` (inclusive of
            # overlapping speech) is the correct field to use here, not
            # `exclusive_speaker_diarization` — VocaDox's own
            # `DiarizationResult`/alignment stage represents overlapping
            # speech honestly via multiple simultaneous turns (see this
            # module's docstring), which `exclusive_speaker_diarization`
            # would silently collapse away.
            diarization = getattr(output, "speaker_diarization", output)

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

            # post-GA P1-2: pyannote.audio 4.x's `DiarizeOutput` also carries
            # `speaker_embeddings`, a per-speaker embedding array aligned to
            # `diarization.labels()`'s sorted label order (documented
            # pyannote.audio 4.x behavior) — previously computed and
            # discarded (see alembic/versions/0013_known_speakers.py). Kept
            # best-effort: any shape/attribute surprise here degrades to "no
            # voiceprint suggestion this run", never a hard failure of
            # diarization itself, since a wrong-shaped embedding used
            # verbatim would risk exactly the silent-misattribution failure
            # mode that migration's docstring warns about.
            speaker_embeddings: dict[str, list[float]] | None = None
            raw_embeddings = getattr(output, "speaker_embeddings", None)
            if raw_embeddings is not None:
                try:
                    sorted_labels = diarization.labels()
                    speaker_embeddings = {
                        label: [float(x) for x in vector]
                        for label, vector in zip(sorted_labels, raw_embeddings, strict=True)
                    }
                except (TypeError, ValueError):
                    speaker_embeddings = None

            return DiarizationResult(
                turns=turns, speaker_count=len(labels), speaker_embeddings=speaker_embeddings
            )

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


@dataclass(frozen=True, slots=True)
class SortformerConfig:
    # Local directory holding the single downloaded `.nemo` checkpoint file
    # (see app.cli.install_models's `diarization-sortformer` profile) —
    # analogous to PyannoteConfig.model_dir, but NeMo ships this model as
    # one self-contained archive rather than a HF "pipeline" of several
    # repos, so there is no separate hf_cache_dir requirement here.
    model_dir: str
    model_name: str = "nvidia/diar_streaming_sortformer_4spk-v2"
    model_revision: str = "5240a64075176943f677d30fa2171c780229f341"
    checkpoint_filename: str = "diar_streaming_sortformer_4spk-v2.nemo"
    device: str = "auto"
    # Streaming-inference parameters, in 80ms frames — values below are the
    # model card's own documented defaults (see ADR-0048), not independently
    # tuned by VocaDox. Kept configurable because the model card documents a
    # genuine latency/accuracy tradeoff range (0.32s-30.4s) a future R-series
    # phase may want to sweep.
    chunk_len: int = 340
    chunk_right_context: int = 40
    fifo_len: int = 40
    spkcache_update_period: int = 300


class SortformerDiarizationProvider(DiarizationProvider):
    """Real local diarization via NVIDIA NeMo's Streaming Sortformer
    4-Speaker v2 model, loaded from a locally-installed `.nemo` checkpoint
    (never downloaded from Hugging Face at request time in production —
    same "admin installs explicitly" policy as
    `PyannoteDiarizationProvider`, see docs/admin/model-installation.md).

    R1 disclosure (see PHASE_R1_VALIDATION_REPORT.md): the `diarize()`
    implementation below follows the model card's own documented usage
    pattern (`SortformerEncLabelModel.diarize(audio=[path])`, plus the
    streaming-config attributes set before inference) as faithfully as
    possible, but real end-to-end inference was never actually executed
    against this code in R1's development sandbox — no GPU, no
    `nemo_toolkit` install, and no model download were available there.
    This mirrors exactly how `PyannoteDiarizationProvider` was first
    disclosed before Phase 3.1 closed the gap with a real Hugging Face
    token and a real installed pipeline; the equivalent closing step here
    is `tools/dev/fastmss/` + a real `.nemo` install (see the ADR).
    """

    def __init__(self, config: SortformerConfig) -> None:
        self._config = config
        self._model: Any = None

    def _checkpoint_path(self) -> Any:
        from pathlib import Path

        return Path(self._config.model_dir) / self._config.checkpoint_filename

    def _is_installed(self) -> bool:
        path = self._checkpoint_path()
        return path.exists() and path.is_file() and path.stat().st_size > 0

    def _resolved_device(self) -> str:
        from app.providers.device import select_device

        if self._config.device == "auto":
            return select_device(prefer_gpu=True)
        return self._config.device

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model
        if not self._is_installed():
            raise DiarizationModelUnavailableError(
                f"diarization model not installed at {self._checkpoint_path()} — run "
                "`docker compose run --rm model-manager install diarization-sortformer` "
                "(see docs/admin/model-installation.md)"
            )
        try:
            from nemo.collections.asr.models import SortformerEncLabelModel
        except ImportError as exc:  # pragma: no cover
            raise DiarizationModelUnavailableError(
                "nemo_toolkit (NeMo) is not installed in this environment"
            ) from exc

        try:
            # `.restore_from()` is NeMo's standard fully-offline single-file
            # checkpoint loader (the `.nemo` archive is a self-contained
            # tarball of weights + config) -- deliberately used instead of
            # `from_pretrained(repo_id)`, which would resolve against
            # Hugging Face at call time; VocaDox never lets a worker reach
            # the network at inference time (same policy as
            # PyannoteDiarizationProvider/_offline_env.py).
            model = SortformerEncLabelModel.restore_from(
                restore_path=str(self._checkpoint_path()),
                map_location=self._resolved_device(),
            )
        except Exception as exc:  # noqa: BLE001
            raise DiarizationModelUnavailableError(
                f"failed to load diarization model: {exc}"
            ) from exc

        model.eval()
        # Model card's own documented streaming defaults (see SortformerConfig).
        model.sortformer_modules.chunk_len = self._config.chunk_len
        model.sortformer_modules.chunk_right_context = self._config.chunk_right_context
        model.sortformer_modules.fifo_len = self._config.fifo_len
        model.sortformer_modules.spkcache_update_period = self._config.spkcache_update_period
        self._model = model
        return self._model

    async def diarize(
        self,
        media_path: str,
        *,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult:
        import asyncio

        def _run() -> DiarizationResult:
            model = self._ensure_loaded()
            # This model is a fixed 4-speaker-max architecture (no
            # min/max_speakers hint API documented on the model card) --
            # both parameters are accepted for interface conformance
            # (DiarizationProvider.diarize's shared signature) but have no
            # effect here, same honest "not supported by this provider"
            # posture as any parameter a given provider can't act on.
            _ = (min_speakers, max_speakers)

            predicted_segments = model.diarize(audio=[media_path], batch_size=1)

            turns: list[SpeakerTurn] = []
            labels: set[str] = set()
            # Real output shape (verified against a real installed
            # checkpoint, not just the model card): predicted_segments[0] is
            # a list of single space-separated strings, one per segment --
            # "<start_seconds> <end_seconds> speaker_<index>", e.g.
            # "0.080 1.200 speaker_0" -- NOT a list of (start, end, index)
            # tuples as the model card's prose suggested. Indexing a string
            # by position (segment[0]/[1]/[2]) silently reads its first
            # three *characters* instead of its three fields, which is why
            # this previously raised "could not convert string to float:
            # '.'" on every real fixture the R0 eval framework was pointed
            # at -- this provider had never actually been run against real
            # audio before that.
            for segment in predicted_segments[0]:
                start_str, end_str, speaker_str = segment.split()
                label = f"SPEAKER_{speaker_str.rsplit('_', 1)[-1].zfill(2)}"
                labels.add(label)
                turns.append(
                    SpeakerTurn(
                        start_seconds=float(start_str),
                        end_seconds=float(end_str),
                        speaker_label=label,
                        # No per-turn confidence score documented for this
                        # model's diarize() output -- same honest 1.0
                        # placeholder PyannoteDiarizationProvider uses,
                        # never a fabricated calibrated value.
                        confidence=1.0,
                    )
                )

            # No per-speaker embedding extraction API documented on this
            # model card (unlike pyannote.audio 4.x's DiarizeOutput) --
            # voiceprint-suggestion embeddings are simply absent for this
            # provider, same honest `None` PyannoteDiarizationProvider
            # returns when its own best-effort extraction fails.
            return DiarizationResult(
                turns=turns, speaker_count=len(labels), speaker_embeddings=None
            )

        return await asyncio.to_thread(_run)

    def status(self) -> DiarizationProviderStatus:
        installed = self._is_installed()
        return DiarizationProviderStatus(
            provider="nvidia-sortformer",
            model=self._config.model_name,
            model_revision=self._config.model_revision,
            installed=installed,
            detail=None if installed else "model not installed at configured model_dir",
        )
