"""RTTM (Rich Transcription Time Marked) parsing -- the standard NIST/DIHARD
ground-truth format for diarization (what FastMSS's `save_rttm=true` option
emits, see `tools/dev/fastmss/README.md`, and what most published diarization
corpora ship). Pure stdlib -- this is a plain whitespace-delimited text
format, no library needed.

Only the `SPEAKER` line type is parsed (the only one diarization ground
truth needs); any other line type (`SPKR-INFO`, `NOISE`, ...) is ignored
rather than rejected, matching how every RTTM consumer in this ecosystem
(dscore, pyannote.metrics) behaves.
"""

from __future__ import annotations

from app.analytics.diarization_metrics import DiarizationTurn


def parse_rttm(text: str) -> list[DiarizationTurn]:
    """Parses RTTM `SPEAKER` lines:

        SPEAKER <file-id> <channel> <turn-onset> <turn-duration> <NA> <NA> <speaker-id> <NA> <NA>

    e.g.:

        SPEAKER meeting_003 1 12.340 3.210 <NA> <NA> spk1 <NA> <NA>

    `<file-id>` is ignored (one RTTM file is always one fixture in this
    project's usage -- see `app.analytics.diarization_fixtures`); malformed
    or short lines are skipped rather than raising, since ground-truth RTTM
    files are hand-curated/tool-generated data, not user input that must be
    strictly validated.
    """
    turns: list[DiarizationTurn] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("SPEAKER"):
            continue
        fields = stripped.split()
        if len(fields) < 8:
            continue
        try:
            onset = float(fields[3])
            duration = float(fields[4])
        except ValueError:
            continue
        if duration <= 0:
            continue
        speaker_id = fields[7]
        turns.append(
            DiarizationTurn(
                start_seconds=onset,
                end_seconds=onset + duration,
                speaker_label=speaker_id,
            )
        )
    return turns


def format_rttm(turns: list[DiarizationTurn], *, file_id: str) -> str:
    """Inverse of `parse_rttm` -- used by
    `tools/dev/fastmss/convert_fixture.py` when normalizing a
    provider's/tool's own turn representation into a `.rttm` fixture file,
    and by tests constructing fixtures inline."""
    lines = []
    for t in turns:
        duration = t.end_seconds - t.start_seconds
        lines.append(
            f"SPEAKER {file_id} 1 {t.start_seconds:.3f} {duration:.3f} "
            f"<NA> <NA> {t.speaker_label} <NA> <NA>"
        )
    return "\n".join(lines) + ("\n" if lines else "")
