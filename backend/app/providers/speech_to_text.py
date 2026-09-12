"""Speech-to-text provider abstraction.

`TranscriptionResult` is the one internal normalized contract every real
provider must produce (spec, "Speech normalized result contract") —
provider-specific values (e.g. faster-whisper's internal segment/word
objects, VAD parameters, beam search internals) must never leak past this
boundary into domain code. Anything provider-specific that's still worth
keeping is captured only in `ProcessingRun.configuration_snapshot`
(app.processing.models), never on the normalized result itself.

`FasterWhisperSpeechProvider` (real, local, offline-capable once the
model is installed — see docs/admin/model-installation.md and
docs/architecture/adr/0016-speech-provider-selection.md for the full
evaluation) is the Phase 3 production provider. `FakeSpeechProvider`
remains available and is what CI/unit tests/GPU-less dev use exclusively
— never the real provider (see .github/workflows/ci.yml).

`NemotronSpeechProvider` (R2, research roadmap, post-GA — see
docs/architecture/adr/0049-nemotron-second-stt-provider.md) is a SECOND,
genuinely independent `SpeechToTextProvider` implementation, wrapping
NVIDIA NeMo's `nvidia/nemotron-3.5-asr-streaming-0.6b` (OpenMDW-1.1, not
gated — verified directly against the license text and the Hugging Face
model API, see the ADR) the same way `FasterWhisperSpeechProvider` wraps
faster-whisper: a locally-installed `.nemo` checkpoint, loaded fully
offline via NeMo's own generic `ASRModel.restore_from()` API (never
downloaded at request time), never assumed installed. **Real NeMo ASR
inference was NOT executed in R2's own development sandbox** (no GPU, no
`nemo_toolkit` install, no model download available there) — this
implementation follows the model card's documented usage pattern as
faithfully as possible but is honestly unverified end-to-end; see
PHASE_R2_VALIDATION_REPORT.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpeechModelUnavailableError(RuntimeError):
    """Raised when the configured speech model is not installed/loadable.
    Callers (the worker) must catch this and classify the job failure as
    MODEL_UNAVAILABLE (app.processing.models.FailureClass) — never crash
    the worker process."""


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    start_seconds: float
    end_seconds: float
    confidence: float


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A single transcribed span. Mirrors the eventual transcript_segments
    table shape. `words` is empty when the provider/model doesn't support
    word-level timestamps — callers must not assume it is always
    populated."""

    start_seconds: float
    end_seconds: float
    text: str
    confidence: float
    words: tuple[Word, ...] = ()
    provider_segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str
    language_confidence: float | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SpeechProviderStatus:
    """What the admin provider-status page renders (spec: "Speech
    (Provider/Model/Status/Device)"). Never a fake "Healthy" if the model
    isn't installed."""

    provider: str
    model: str
    model_revision: str | None
    installed: bool
    device: str
    cuda_available: bool
    detail: str | None = None


class SpeechToTextProvider(ABC):
    """Real implementations (Whisper, ...) land in Phase 3. Interface only here."""

    @abstractmethod
    async def transcribe(
        self,
        media_path: str,
        *,
        language_hint: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """`hotwords`/`initial_prompt` (post-GA P0-3) carry an org/
        template-resolved custom vocabulary (app.vocabulary.service
        .resolve_vocabulary) straight through to the underlying model,
        unmodified -- never reinterpreted or scored here."""
        raise NotImplementedError

    @abstractmethod
    def status(self) -> SpeechProviderStatus:
        raise NotImplementedError


class FakeSpeechProvider(SpeechToTextProvider):
    """Deterministic synthetic transcription for tests and local dev --
    accepts `hotwords`/`initial_prompt` (so pipeline wiring can be tested)
    but never lets them change the output, staying fully deterministic."""

    async def transcribe(
        self,
        media_path: str,
        *,
        language_hint: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[
                TranscriptSegment(
                    0.0,
                    2.5,
                    "This is a fake transcript segment.",
                    0.99,
                    words=(
                        Word("This", 0.0, 0.3, 0.99),
                        Word("is", 0.3, 0.5, 0.99),
                        Word("a", 0.5, 0.6, 0.99),
                        Word("fake", 0.6, 1.0, 0.99),
                        Word("transcript", 1.0, 1.8, 0.99),
                        Word("segment.", 1.8, 2.5, 0.99),
                    ),
                    provider_segment_id="0",
                ),
                TranscriptSegment(
                    2.5,
                    5.0,
                    "Generated deterministically for tests.",
                    0.98,
                    words=(
                        Word("Generated", 2.5, 3.2, 0.98),
                        Word("deterministically", 3.2, 4.3, 0.98),
                        Word("for", 4.3, 4.6, 0.98),
                        Word("tests.", 4.6, 5.0, 0.98),
                    ),
                    provider_segment_id="1",
                ),
            ],
            language=language_hint or "en",
            language_confidence=1.0,
            duration_ms=5000,
        )

    def status(self) -> SpeechProviderStatus:
        return SpeechProviderStatus(
            provider="fake",
            model="fake-deterministic",
            model_revision=None,
            installed=True,
            device="cpu",
            cuda_available=False,
            detail="Deterministic fake provider for tests/dev — never used in production.",
        )


@dataclass(frozen=True, slots=True)
class FasterWhisperConfig:
    """Everything needed to load/describe the real provider without
    hardcoding a model identifier anywhere in worker code (spec: "don't
    hardcode model identifiers in worker code")."""

    model_dir: str  # local path under the persistent model volume
    model_name: str = "Systran/faster-whisper-small"
    model_revision: str = "536b0662742c02347bc0e980a01041f333bce12"
    device: str = "auto"  # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"  # let ctranslate2 pick int8/float16 per device
    beam_size: int = 5
    vad_filter: bool = True


class FasterWhisperSpeechProvider(SpeechToTextProvider):
    """Real local STT via faster-whisper (CTranslate2 Whisper). See
    docs/architecture/adr/0016-speech-provider-selection.md for the full
    evaluation and docs/admin/model-installation.md for how the model gets
    onto `config.model_dir` (never downloaded silently at request time in
    production)."""

    def __init__(self, config: FasterWhisperConfig) -> None:
        self._config = config
        self._model = None  # lazy-loaded, see _ensure_loaded

    def _model_path(self) -> Path:
        return Path(self._config.model_dir)

    def _is_installed(self) -> bool:
        path = self._model_path()
        return path.exists() and (path / "model.bin").exists()

    def _resolved_device(self) -> str:
        from app.providers.device import select_device

        if self._config.device == "auto":
            return select_device(prefer_gpu=True)
        return self._config.device

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model
        if not self._is_installed():
            raise SpeechModelUnavailableError(
                f"speech model not installed at {self._model_path()} — run "
                "`vocadox models install speech-default` (see docs/admin/model-installation.md)"
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - exercised only when dep is missing
            raise SpeechModelUnavailableError(
                "faster-whisper is not installed in this environment"
            ) from exc

        device = self._resolved_device()
        compute_type = self._config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        try:
            self._model = WhisperModel(
                str(self._model_path()), device=device, compute_type=compute_type
            )
        except Exception as exc:  # noqa: BLE001
            raise SpeechModelUnavailableError(f"failed to load speech model: {exc}") from exc
        return self._model

    async def transcribe(
        self,
        media_path: str,
        *,
        language_hint: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        import asyncio

        def _run() -> TranscriptionResult:
            model = self._ensure_loaded()
            segments_iter, info = model.transcribe(
                media_path,
                language=language_hint,
                beam_size=self._config.beam_size,
                vad_filter=self._config.vad_filter,
                word_timestamps=True,
                hotwords=hotwords,
                initial_prompt=initial_prompt,
            )
            segments: list[TranscriptSegment] = []
            for i, seg in enumerate(segments_iter):
                words = tuple(
                    Word(
                        text=w.word.strip(),
                        start_seconds=w.start,
                        end_seconds=w.end,
                        confidence=float(getattr(w, "probability", 0.0) or 0.0),
                    )
                    for w in (seg.words or [])
                )
                confidence = 0.0
                if words:
                    confidence = sum(w.confidence for w in words) / len(words)
                elif hasattr(seg, "avg_logprob"):
                    # avg_logprob is a log-probability (<= 0); map to a rough
                    # (0,1] confidence proxy only when no word-level scores
                    # exist. Documented as an approximation, not calibrated.
                    import math

                    confidence = math.exp(seg.avg_logprob)
                segments.append(
                    TranscriptSegment(
                        start_seconds=seg.start,
                        end_seconds=seg.end,
                        text=seg.text.strip(),
                        confidence=confidence,
                        words=words,
                        provider_segment_id=str(i),
                    )
                )
            duration_ms = int(info.duration * 1000) if getattr(info, "duration", None) else None
            return TranscriptionResult(
                segments=segments,
                language=info.language or (language_hint or "unknown"),
                language_confidence=float(getattr(info, "language_probability", 0.0) or 0.0),
                duration_ms=duration_ms,
            )

        return await asyncio.to_thread(_run)

    def status(self) -> SpeechProviderStatus:
        installed = self._is_installed()
        device = self._resolved_device()
        from app.providers.device import detect_device_capabilities

        caps = detect_device_capabilities()
        return SpeechProviderStatus(
            provider="faster-whisper",
            model=self._config.model_name,
            model_revision=self._config.model_revision,
            installed=installed,
            device=device,
            cuda_available=caps.cuda_available,
            detail=None if installed else "model not installed at configured model_dir",
        )


@dataclass(frozen=True, slots=True)
class NemotronConfig:
    # Local directory holding the single downloaded `.nemo` checkpoint file
    # (see app.cli.install_models's `stt-nemotron` profile) — analogous to
    # SortformerConfig.model_dir: NeMo ships this model as one
    # self-contained archive, not a HF "pipeline" of several repos, so
    # there is no separate hf_cache_dir requirement here (unlike
    # FasterWhisperConfig, which is a CTranslate2 snapshot directory, or
    # pyannote's multi-repo cache).
    model_dir: str
    model_name: str = "nvidia/nemotron-3.5-asr-streaming-0.6b"
    model_revision: str = "ea30d66debe3740a08b573244286791d423d6b3e"
    checkpoint_filename: str = "nemotron-3.5-asr-streaming-0.6b.nemo"
    device: str = "auto"


class NemotronSpeechProvider(SpeechToTextProvider):
    """Real local STT via NVIDIA NeMo's Nemotron 3.5 ASR Streaming 0.6B
    model, loaded from a locally-installed `.nemo` checkpoint (never
    downloaded from Hugging Face at request time in production — same
    "admin installs explicitly" policy as `FasterWhisperSpeechProvider`,
    see docs/admin/model-installation.md).

    R2 disclosure (see PHASE_R2_VALIDATION_REPORT.md): `transcribe()`
    below follows the model card's own documented usage pattern
    (`nemo_asr.models.ASRModel.from_pretrained(...).transcribe([path])`)
    as faithfully as possible, but loads fully offline via NeMo's generic
    `.restore_from()` checkpoint loader instead (same "never let a worker
    reach the network at inference time" policy
    `SortformerDiarizationProvider`/`_offline_env.py` already enforce).
    Real end-to-end inference was never actually executed against this
    code in R2's development sandbox — no GPU, no `nemo_toolkit` install,
    and no model download were available there. This mirrors exactly how
    `SortformerDiarizationProvider` was disclosed in R1.

    Two honest gaps versus `FasterWhisperSpeechProvider`, disclosed rather
    than papered over:

    - **No documented word- or segment-level timestamp/confidence API** in
      the model card's simplest, documented `.transcribe(paths)` usage
      sample (unlike faster-whisper's `segments`/`words` objects) — the
      whole file is reported as a single segment with an honest `0.0`
      placeholder confidence and no `words`, never fabricated per-word
      timing this API does not document providing.
    - **No documented duration/end-timestamp** from that same call — this
      provider does not independently probe the audio file's duration
      (that would require adding a new dependency or shelling out to
      ffprobe, out of scope for this PoC — see
      docs/architecture/adr/0049-nemotron-second-stt-provider.md), so
      `end_seconds`/`duration_ms` are honestly `0.0`/`None` rather than
      guessed.
    - **`hotwords`/`initial_prompt` are accepted but unused**: no
      documented custom-vocabulary biasing API on this model card's basic
      usage path, unlike faster-whisper's `hotwords`/`initial_prompt`
      params — same honest "not supported by this provider" posture
      `SortformerDiarizationProvider` uses for `min_speakers`/
      `max_speakers`.
    """

    def __init__(self, config: NemotronConfig) -> None:
        self._config = config
        self._model: Any = None

    def _checkpoint_path(self) -> Path:
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
            raise SpeechModelUnavailableError(
                f"speech model not installed at {self._checkpoint_path()} — run "
                "`docker compose run --rm model-manager install stt-nemotron` "
                "(see docs/admin/model-installation.md)"
            )
        try:
            from nemo.collections.asr.models import ASRModel
        except ImportError as exc:  # pragma: no cover
            raise SpeechModelUnavailableError(
                "nemo_toolkit (NeMo) is not installed in this environment"
            ) from exc

        try:
            # `.restore_from()` is NeMo's standard fully-offline single-file
            # checkpoint loader (the `.nemo` archive is a self-contained
            # tarball of weights + config); the generic `ASRModel` base
            # class dispatches to the checkpoint's own recorded concrete
            # class at load time (documented NeMo behavior), the same
            # reason `SortformerDiarizationProvider` uses NeMo's own
            # concrete-class loader rather than reimplementing model
            # introspection here. Deliberately not
            # `from_pretrained(model_name=...)`, which would resolve
            # against Hugging Face at call time.
            model = ASRModel.restore_from(
                restore_path=str(self._checkpoint_path()),
                map_location=self._resolved_device(),
            )
        except Exception as exc:  # noqa: BLE001
            raise SpeechModelUnavailableError(f"failed to load speech model: {exc}") from exc

        model.eval()
        self._model = model
        return self._model

    async def transcribe(
        self,
        media_path: str,
        *,
        language_hint: str | None = None,
        hotwords: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        import asyncio

        def _run() -> TranscriptionResult:
            model = self._ensure_loaded()
            # No documented custom-vocabulary biasing API on this model
            # card's basic usage path -- see class docstring.
            _ = (hotwords, initial_prompt)

            output = model.transcribe([media_path], batch_size=1)

            # Model card's simplest documented usage sample returns a
            # plain list[str] (one transcript string per input file).
            # Some NeMo versions instead return a list of `Hypothesis`
            # objects with a `.text` attribute for the same call -- both
            # are handled here rather than assuming one shape, the same
            # defensive posture `PyannoteDiarizationProvider` uses for its
            # own library-version output-shape quirk.
            raw = output[0] if output else ""
            text = str(getattr(raw, "text", raw)).strip()

            segments: list[TranscriptSegment] = []
            if text:
                segments.append(
                    TranscriptSegment(
                        start_seconds=0.0,
                        end_seconds=0.0,  # unknown -- see class docstring
                        text=text,
                        confidence=0.0,  # unknown -- see class docstring
                        words=(),
                        provider_segment_id="0",
                    )
                )

            return TranscriptionResult(
                segments=segments,
                language=language_hint or "auto",
                language_confidence=None,
                duration_ms=None,
            )

        return await asyncio.to_thread(_run)

    def status(self) -> SpeechProviderStatus:
        installed = self._is_installed()
        device = self._resolved_device()
        from app.providers.device import detect_device_capabilities

        caps = detect_device_capabilities()
        return SpeechProviderStatus(
            provider="nvidia-nemotron",
            model=self._config.model_name,
            model_revision=self._config.model_revision,
            installed=installed,
            device=device,
            cuda_available=caps.cuda_available,
            detail=None if installed else "model not installed at configured model_dir",
        )
