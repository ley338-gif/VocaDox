"""R2 (research roadmap, post-GA): unit tests for NemotronSpeechProvider
and its wiring into app.core.ai_providers.get_speech_provider.

These deliberately never import/require `nemo_toolkit` (not installed in the
mandatory CI test environment, same policy as faster-whisper/pyannote/
Sortformer — see docs/architecture/adr/0016-speech-provider-selection.md's
"Consequences" and PHASE_R1_VALIDATION_REPORT.md): they exercise only the
not-installed / status paths, which never touch the real NeMo import. Real
inference against an actually-installed `.nemo` checkpoint is out of scope
for the mandatory suite by design, exactly like SortformerDiarizationProvider.
"""

from __future__ import annotations

import pytest
from app.providers.speech_to_text import (
    NemotronConfig,
    NemotronSpeechProvider,
    SpeechModelUnavailableError,
)


def test_nemotron_status_reports_not_installed_when_checkpoint_missing(tmp_path) -> None:
    provider = NemotronSpeechProvider(NemotronConfig(model_dir=str(tmp_path)))
    status = provider.status()
    assert status.provider == "nvidia-nemotron"
    assert status.model == "nvidia/nemotron-3.5-asr-streaming-0.6b"
    assert status.installed is False
    assert status.detail is not None


def test_nemotron_status_reports_installed_when_checkpoint_present(tmp_path) -> None:
    checkpoint = tmp_path / "nemotron-3.5-asr-streaming-0.6b.nemo"
    checkpoint.write_bytes(b"not-a-real-checkpoint-but-non-empty")
    provider = NemotronSpeechProvider(NemotronConfig(model_dir=str(tmp_path)))
    status = provider.status()
    assert status.installed is True
    assert status.detail is None


async def test_nemotron_transcribe_raises_clear_error_when_not_installed(tmp_path) -> None:
    provider = NemotronSpeechProvider(NemotronConfig(model_dir=str(tmp_path)))
    with pytest.raises(SpeechModelUnavailableError, match="not installed"):
        await provider.transcribe("irrelevant.wav")


def test_get_speech_provider_selects_nemotron(monkeypatch, tmp_path) -> None:
    """app.core.ai_providers.get_speech_provider — the one place
    VOCADOX_SPEECH_PROVIDER is read — must actually construct a
    NemotronSpeechProvider for 'nemotron', not just 'fake'/'faster_whisper'."""
    from app.core import ai_providers
    from app.platform.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VOCADOX_SPEECH_PROVIDER", "nemotron")
    monkeypatch.setenv("VOCADOX_MODEL_VOLUME_ROOT", str(tmp_path))
    try:
        provider = ai_providers.get_speech_provider()
        assert isinstance(provider, NemotronSpeechProvider)
    finally:
        get_settings.cache_clear()
