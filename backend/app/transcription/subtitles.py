"""SRT/VTT subtitle rendering (post-GA P0-2) -- pure string formatting,
no new dependency; both formats are simple enough to hand-write directly
from `TranscriptSegment.start_ms`/`end_ms` (already millisecond-precise
from alignment) without a subtitle library.
"""

from __future__ import annotations

from app.transcription.models import TranscriptSegment


def _segment_text(segment: TranscriptSegment) -> str:
    return segment.corrected_text or segment.original_text


def _srt_timestamp(ms: int) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _vtt_timestamp(ms: int) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def render_srt(segments: list[TranscriptSegment]) -> str:
    blocks = [
        f"{i}\n{_srt_timestamp(s.start_ms)} --> {_srt_timestamp(s.end_ms)}\n{_segment_text(s)}"
        for i, s in enumerate(segments, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_vtt(segments: list[TranscriptSegment]) -> str:
    blocks = [
        f"{_vtt_timestamp(s.start_ms)} --> {_vtt_timestamp(s.end_ms)}\n{_segment_text(s)}"
        for s in segments
    ]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + ("\n" if blocks else "")
