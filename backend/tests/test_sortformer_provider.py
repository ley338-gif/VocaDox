"""R1 (research roadmap, post-GA): unit tests for SortformerDiarizationProvider
and its wiring into app.core.ai_providers.get_diarization_provider.

These deliberately never import/require `nemo_toolkit` (not installed in the
mandatory CI test environment, same policy as pyannote.audio — see
docs/architecture/adr/0017-diarization-provider-selection.md's "Consequences"
and PHASE_R1_VALIDATION_REPORT.md): they exercise only the not-installed /
status paths, which never touch the real NeMo import. Real inference against
an actually-installed `.nemo` checkpoint is out of scope for the mandatory
suite by design, exactly like PyannoteDiarizationProvider.
"""

from __future__ import annotations

import pytest
from app.providers.diarization import (
    DiarizationModelUnavailableError,
    SortformerConfig,
    SortformerDiarizationProvider,
)


def test_sortformer_status_reports_not_installed_when_checkpoint_missing(tmp_path) -> None:
    provider = SortformerDiarizationProvider(SortformerConfig(model_dir=str(tmp_path)))
    status = provider.status()
    assert status.provider == "nvidia-sortformer"
    assert status.model == "nvidia/diar_streaming_sortformer_4spk-v2"
    assert status.installed is False
    assert status.detail is not None


def test_sortformer_status_reports_installed_when_checkpoint_present(tmp_path) -> None:
    checkpoint = tmp_path / "diar_streaming_sortformer_4spk-v2.nemo"
    checkpoint.write_bytes(b"not-a-real-checkpoint-but-non-empty")
    provider = SortformerDiarizationProvider(SortformerConfig(model_dir=str(tmp_path)))
    status = provider.status()
    assert status.installed is True
    assert status.detail is None


async def test_sortformer_diarize_raises_clear_error_when_not_installed(tmp_path) -> None:
    provider = SortformerDiarizationProvider(SortformerConfig(model_dir=str(tmp_path)))
    with pytest.raises(DiarizationModelUnavailableError, match="not installed"):
        await provider.diarize("irrelevant.wav")


def test_get_diarization_provider_selects_sortformer(monkeypatch, tmp_path) -> None:
    """app.core.ai_providers.get_diarization_provider — the one place
    VOCADOX_DIARIZATION_PROVIDER is read — must actually construct a
    SortformerDiarizationProvider for 'sortformer', not just 'fake'/'pyannote'."""
    from app.core import ai_providers
    from app.platform.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VOCADOX_DIARIZATION_PROVIDER", "sortformer")
    monkeypatch.setenv("VOCADOX_MODEL_VOLUME_ROOT", str(tmp_path))
    try:
        provider = ai_providers.get_diarization_provider()
        assert isinstance(provider, SortformerDiarizationProvider)
    finally:
        get_settings.cache_clear()
