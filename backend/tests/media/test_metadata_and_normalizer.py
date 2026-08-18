from __future__ import annotations

from app.media.metadata import extract_audio_metadata
from app.media.normalizer import NoOpMediaNormalizer, NormalizationInput

from tests.conversations.conftest import make_wav_bytes


async def test_noop_normalizer_passes_through_unchanged() -> None:
    normalizer = NoOpMediaNormalizer()
    data = make_wav_bytes()
    result = await normalizer.normalize(
        NormalizationInput(data=data, content_type="audio/wav", container="wav")
    )
    assert result.data == data
    assert result.content_type == "audio/wav"
    assert result.container == "wav"


def test_extract_audio_metadata_wav() -> None:
    data = make_wav_bytes(duration_s=1.0, sample_rate=16000)
    meta = extract_audio_metadata(data, container="wav")
    assert meta.sample_rate == 16000
    assert meta.channels == 1
    assert meta.duration_ms is not None and 900 <= meta.duration_ms <= 1100


def test_extract_audio_metadata_never_raises_on_garbage() -> None:
    meta = extract_audio_metadata(b"not really audio", container="mp3")
    # Best-effort: garbage input yields empty metadata, never an exception.
    assert meta.duration_ms is None
