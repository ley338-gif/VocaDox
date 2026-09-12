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


async def test_sortformer_diarize_parses_real_output_format(tmp_path, monkeypatch) -> None:
    """Regression test for a real bug found by running this provider
    against real audio for the first time (2026-09-12, post-R1 empirical
    validation): `SortformerEncLabelModel.diarize()` returns
    `predicted_segments[0]` as a list of single space-separated strings
    like "0.080 1.200 speaker_0" -- NOT a list of (start, end, index)
    tuples as the model card's prose had suggested and the original R1
    implementation assumed. Indexing a string by position
    (segment[0]/[1]/[2]) silently read its first three *characters*
    instead of splitting it, raising `ValueError: could not convert string
    to float: '.'` on every real fixture. Never caught by CI because no
    prior test exercised real (or even realistically-shaped fake) output
    from `.diarize()` — every existing test in this file only reaches the
    not-installed/status paths."""
    checkpoint = tmp_path / "diar_streaming_sortformer_4spk-v2.nemo"
    checkpoint.write_bytes(b"not-a-real-checkpoint-but-non-empty")
    provider = SortformerDiarizationProvider(SortformerConfig(model_dir=str(tmp_path)))

    class _FakeModel:
        def diarize(self, audio, batch_size):
            return [
                [
                    "0.080 1.200 speaker_0",
                    "2.080 14.720 speaker_1",
                    "15.440 16.320 speaker_0",
                ]
            ]

    monkeypatch.setattr(provider, "_ensure_loaded", lambda: _FakeModel())

    result = await provider.diarize("irrelevant.wav")

    assert result.speaker_count == 2
    assert [t.speaker_label for t in result.turns] == [
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_00",
    ]
    assert result.turns[0].start_seconds == pytest.approx(0.080)
    assert result.turns[0].end_seconds == pytest.approx(1.200)
    assert result.turns[1].start_seconds == pytest.approx(2.080)
    assert result.turns[1].end_seconds == pytest.approx(14.720)


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
