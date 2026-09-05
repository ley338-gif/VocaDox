"""Speech/diarization provider + media-normalizer dependency-injection
wiring. Lives in `app/core` (cross-cutting, not a domain package — see
app/core/storage.py for the identical precedent) so domain code never
imports a concrete provider implementation directly (enforced by
tests/test_architecture_boundaries.py).

`get_speech_provider`/`get_diarization_provider` read
`Settings.speech_provider`/`diarization_provider` ("fake" | real) — CI and
unit tests always run with "fake" (the default), so no GPU/model
dependency is ever required to run the mandatory test suite.
"""

from __future__ import annotations

from pathlib import Path

from app.media.normalizer import FfmpegMediaNormalizer, MediaNormalizer, NoOpMediaNormalizer
from app.platform.config import get_settings
from app.platform.valkey.backends import QueueBackend
from app.platform.valkey.valkey_backend import get_valkey_backend
from app.providers.diarization import (
    DiarizationProvider,
    FakeDiarizationProvider,
    PyannoteConfig,
    PyannoteDiarizationProvider,
)
from app.providers.llm import (
    FakeLLMProvider,
    LLMModelUnavailableError,
    LLMProvider,
    OllamaConfig,
    OllamaLLMProvider,
)
from app.providers.speech_to_text import (
    FakeSpeechProvider,
    FasterWhisperConfig,
    FasterWhisperSpeechProvider,
    SpeechToTextProvider,
)


def get_queue_backend() -> QueueBackend:
    return get_valkey_backend()


def get_speech_provider() -> SpeechToTextProvider:
    settings = get_settings()
    if settings.speech_provider == "faster_whisper":
        model_dir = str(Path(settings.model_volume_root) / settings.speech_model_dir_name)
        return FasterWhisperSpeechProvider(
            FasterWhisperConfig(model_dir=model_dir, device=settings.speech_device)
        )
    return FakeSpeechProvider()


def get_diarization_provider() -> DiarizationProvider:
    settings = get_settings()
    if settings.diarization_provider == "pyannote":
        from app.cli.install_models import hf_cache_dir

        model_dir = str(Path(settings.model_volume_root) / settings.diarization_model_dir_name)
        return PyannoteDiarizationProvider(
            PyannoteConfig(
                model_dir=model_dir,
                device=settings.diarization_device,
                hf_cache_dir=str(hf_cache_dir(Path(settings.model_volume_root))),
            )
        )
    return FakeDiarizationProvider()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        if not settings.llm_base_url:
            # VocaDox no longer bundles an `ollama` Compose service (removed
            # for GA — see docs/architecture/adr/0029-remove-bundled-ollama.md,
            # CVE-2026-56854), so there is no host to silently default to any
            # more. Fail clearly and actionably here, at provider-construction
            # time, rather than handing back a provider that will just time
            # out against an unreachable/made-up URL (same "fail clearly, not
            # silently misbehave" policy as SpeechModelUnavailableError /
            # DiarizationModelUnavailableError — see app.processing.retry).
            raise LLMModelUnavailableError(
                "VOCADOX_LLM_PROVIDER is 'ollama' but VOCADOX_LLM_BASE_URL is not set. "
                "VocaDox does not bundle an Ollama container — point this at your own "
                "admin-managed Ollama instance (e.g. http://localhost:11434 or "
                "http://<host>:11434). See docs/admin/llm-provider.md."
            )
        return OllamaLLMProvider(
            OllamaConfig(
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                timeout_seconds=settings.llm_timeout_seconds,
            )
        )
    return FakeLLMProvider()


def get_llm_provider_for_model_identifier(*, provider: str, model_identifier: str) -> LLMProvider:
    """Phase 8: the Evaluation Lab needs to build a real provider instance
    for an ARBITRARY `ModelProfile` row's own `provider`/`model_identifier`
    (not just the single globally-configured one `get_llm_provider` builds)
    so it can run two genuinely different model configs side by side. Domain
    code (app.analytics) must never construct `OllamaLLMProvider`/
    `FakeLLMProvider` directly (see tests/test_architecture_boundaries.py)
    — this factory is the one place that's allowed to."""
    settings = get_settings()
    if provider == "ollama":
        if not settings.llm_base_url:
            raise LLMModelUnavailableError(
                "ModelProfile requests provider 'ollama' but VOCADOX_LLM_BASE_URL is not "
                "set. VocaDox does not bundle an Ollama container — point this at your own "
                "admin-managed Ollama instance. See docs/admin/llm-provider.md."
            )
        return OllamaLLMProvider(
            OllamaConfig(
                base_url=settings.llm_base_url,
                model=model_identifier,
                timeout_seconds=settings.llm_timeout_seconds,
            )
        )
    return FakeLLMProvider()


def get_media_normalizer() -> MediaNormalizer:
    """FFmpeg-based normalization is used whenever the `ffmpeg` binary is
    resolvable on PATH; otherwise falls back to the Phase 2 no-op
    normalizer (documented, not silent — see FfmpegMediaNormalizer's
    docstring and docs/architecture/adr/0019-ffmpeg-normalization.md)."""
    if FfmpegMediaNormalizer.ffmpeg_available():
        settings = get_settings()
        return FfmpegMediaNormalizer(
            target_sample_rate_hz=settings.normalization_target_sample_rate_hz,
            subprocess_timeout_seconds=settings.normalization_subprocess_timeout_seconds,
        )
    return NoOpMediaNormalizer()
