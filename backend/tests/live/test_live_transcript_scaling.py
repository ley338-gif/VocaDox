from __future__ import annotations

import pytest
from benchmarks.live_transcript_scaling import estimate_scaling


def test_twenty_minute_whole_prefix_work_is_triangular() -> None:
    estimate = estimate_scaling(20, flush_interval_seconds=10, overlap_seconds=2)

    assert estimate.flush_count == 120
    assert estimate.whole_prefix_audio_seconds == 72_600
    assert estimate.whole_prefix_amplification == pytest.approx(60.5)
    assert estimate.rolling_window_audio_seconds == 1_438
    assert estimate.rolling_window_amplification == pytest.approx(1.1983, rel=1e-4)


def test_sixty_minute_upload_volume_at_48_kbps() -> None:
    estimate = estimate_scaling(60, bitrate_kbps=48)

    assert estimate.final_recording_bytes == 21_600_000
    assert estimate.whole_prefix_upload_bytes == 3_898_800_000
    assert estimate.rolling_window_upload_bytes == 25_908_000


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"duration_minutes": 0}, "duration_minutes"),
        ({"duration_minutes": 1, "flush_interval_seconds": 0}, "flush_interval_seconds"),
        ({"duration_minutes": 1, "overlap_seconds": 10}, "overlap_seconds"),
        ({"duration_minutes": 1, "bitrate_kbps": 0}, "bitrate_kbps"),
    ],
)
def test_invalid_scaling_inputs_are_rejected(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        estimate_scaling(**kwargs)
