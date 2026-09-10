"""Deterministic workload model for live-transcript upload/ASR strategies.

This deliberately models *work volume*, not provider wall-clock speed. The
latter depends on the installed model and CPU/GPU. Multiplying audio work by a
measured real-time factor (RTF) gives the corresponding compute time.

Run from ``backend`` with::

    uv run python -m benchmarks.live_transcript_scaling
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScalingEstimate:
    duration_seconds: int
    flush_interval_seconds: int
    overlap_seconds: int
    bitrate_kbps: int
    flush_count: int
    whole_prefix_audio_seconds: int
    rolling_window_audio_seconds: int
    final_recording_bytes: int
    whole_prefix_upload_bytes: int
    rolling_window_upload_bytes: int

    @property
    def whole_prefix_amplification(self) -> float:
        return self.whole_prefix_audio_seconds / self.duration_seconds

    @property
    def rolling_window_amplification(self) -> float:
        return self.rolling_window_audio_seconds / self.duration_seconds


def estimate_scaling(
    duration_minutes: int,
    *,
    flush_interval_seconds: int = 10,
    overlap_seconds: int = 2,
    bitrate_kbps: int = 48,
) -> ScalingEstimate:
    """Return exact work/upload volume for a fixed-cadence recording.

    Whole-prefix work is ``interval * (1 + ... + flush_count)``. The rolling
    design processes each interval once and reprocesses only the overlap after
    the first window. Network byte estimates use the supplied encoded bitrate;
    they intentionally exclude HTTP framing because payload dominates here.
    """
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if flush_interval_seconds <= 0:
        raise ValueError("flush_interval_seconds must be positive")
    if overlap_seconds < 0 or overlap_seconds >= flush_interval_seconds:
        raise ValueError("overlap_seconds must be between 0 and the flush interval")
    if bitrate_kbps <= 0:
        raise ValueError("bitrate_kbps must be positive")

    duration_seconds = duration_minutes * 60
    flush_count = duration_seconds // flush_interval_seconds
    whole_prefix_audio_seconds = (
        flush_interval_seconds * flush_count * (flush_count + 1) // 2
    )
    rolling_window_audio_seconds = duration_seconds + max(0, flush_count - 1) * overlap_seconds
    bytes_per_second = bitrate_kbps * 1000 / 8

    return ScalingEstimate(
        duration_seconds=duration_seconds,
        flush_interval_seconds=flush_interval_seconds,
        overlap_seconds=overlap_seconds,
        bitrate_kbps=bitrate_kbps,
        flush_count=flush_count,
        whole_prefix_audio_seconds=whole_prefix_audio_seconds,
        rolling_window_audio_seconds=rolling_window_audio_seconds,
        final_recording_bytes=round(duration_seconds * bytes_per_second),
        whole_prefix_upload_bytes=round(whole_prefix_audio_seconds * bytes_per_second),
        rolling_window_upload_bytes=round(rolling_window_audio_seconds * bytes_per_second),
    )


def _gib(value: int) -> float:
    return value / (1024**3)


def render_markdown(estimates: list[ScalingEstimate], *, rtf: float) -> str:
    lines = [
        "| Duration | Flushes | Whole-prefix audio work | Whole-prefix amp. | "
        "Rolling audio work | Rolling amp. | Whole upload | Rolling upload | "
        f"Whole compute @ RTF {rtf:g} |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in estimates:
        whole_hours = item.whole_prefix_audio_seconds / 3600
        rolling_hours = item.rolling_window_audio_seconds / 3600
        compute_hours = whole_hours * rtf
        lines.append(
            f"| {item.duration_seconds // 60} min | {item.flush_count} | "
            f"{whole_hours:.2f} h | {item.whole_prefix_amplification:.1f}x | "
            f"{rolling_hours:.2f} h | {item.rolling_window_amplification:.2f}x | "
            f"{_gib(item.whole_prefix_upload_bytes):.2f} GiB | "
            f"{_gib(item.rolling_window_upload_bytes):.3f} GiB | {compute_hours:.2f} h |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--durations", type=int, nargs="+", default=[5, 20, 40, 60])
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--overlap", type=int, default=2)
    parser.add_argument("--bitrate-kbps", type=int, default=48)
    parser.add_argument("--rtf", type=float, default=0.25)
    args = parser.parse_args()
    estimates = [
        estimate_scaling(
            duration,
            flush_interval_seconds=args.interval,
            overlap_seconds=args.overlap,
            bitrate_kbps=args.bitrate_kbps,
        )
        for duration in args.durations
    ]
    print(render_markdown(estimates, rtf=args.rtf))


if __name__ == "__main__":
    main()
