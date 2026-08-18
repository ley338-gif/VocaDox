"""Deterministic ASR + diarization alignment algorithm (Phase 3 core).

Pure functions only — no DB, no I/O, no provider calls — so the algorithm
is unit-testable in isolation from end-to-end processing (see
tests/transcription/test_alignment.py). app.processing orchestrates
calling this after both a SPEECH_TO_TEXT and (optionally) a DIARIZATION
ProcessingRun exist for the same source media, then persists the result as
TranscriptSegment rows.

## Algorithm

Word-level overlap assignment is used whenever the ASR segment has word
timestamps (the common case for faster-whisper); segment-level overlap is
the fallback when it doesn't (spec: "prefer word-level overlap assignment
where word timestamps exist").

For each ASR segment:

1. If there is no diarization result (or it has zero turns), the whole
   segment becomes one output segment with `speaker_label=None`,
   `quality=UNASSIGNED` — never a guessed speaker.

2. Word-level path (segment has words):
   - For every word, compute temporal overlap (in ms) against every
     diarization turn. `dominant_ratio = best_turn_overlap_ms / word_duration_ms`.
   - A word is UNASSIGNED if it overlaps no turn at all.
   - A word is flagged OVERLAP if more than one *distinct speaker label*
     overlaps it (simultaneous speech covers this word's time range).
   - Otherwise a word is CONFIDENT if `dominant_ratio >= CONFIDENT_THRESHOLD`,
     else AMBIGUOUS (weak temporal evidence — never silently upgraded to
     CONFIDENT).
   - Consecutive words are grouped into output segments by
     `(speaker_label)` — i.e. the original ASR segment is *split* exactly
     where the assigned speaker changes, preserving original ASR word
     timing/text on each side (spec: "split transcript segments when
     speaker changes mid-ASR-segment... preserve original ASR timing").
   - Each resulting sub-segment's quality is the "worst" quality among its
     words, in priority order OVERLAP > AMBIGUOUS > UNASSIGNED > CONFIDENT
     — i.e. if the sub-segment is entirely CONFIDENT words with the same
     speaker, it's CONFIDENT; a single AMBIGUOUS or OVERLAP word downgrades
     the whole sub-segment, since a reviewer needs to see the segment to
     resolve it, not just the one weak word.

3. Segment-level path (no word timestamps): identical overlap logic
   applied to the segment's own [start, end] range as if it were a single
   "word" — cannot split mid-segment without word timing, so the whole
   segment gets one speaker/quality decision. Documented limitation, not a
   silent gap.

`CONFIDENT_THRESHOLD` and the OVERLAP/AMBIGUOUS/UNASSIGNED semantics are
intentionally conservative: this becomes Review data (spec, "Low-
confidence review foundation") — the algorithm's job is to be honest about
uncertainty, not to force a speaker label onto every word.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.providers.diarization import DiarizationResult, SpeakerTurn
from app.providers.speech_to_text import TranscriptionResult, TranscriptSegment, Word

CONFIDENT_THRESHOLD = 0.66


class AlignmentQuality(StrEnum):
    CONFIDENT = "confident"
    AMBIGUOUS = "ambiguous"
    OVERLAP = "overlap"
    UNASSIGNED = "unassigned"


_QUALITY_PRIORITY = {
    AlignmentQuality.OVERLAP: 3,
    AlignmentQuality.AMBIGUOUS: 2,
    AlignmentQuality.UNASSIGNED: 1,
    AlignmentQuality.CONFIDENT: 0,
}


@dataclass(frozen=True, slots=True)
class AlignedWord:
    text: str
    start_ms: int
    end_ms: int
    confidence: float
    speaker_label: str | None
    quality: AlignmentQuality


@dataclass(frozen=True, slots=True)
class AlignedSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    speaker_label: str | None
    quality: AlignmentQuality
    words: list[AlignedWord] = field(default_factory=list)


def _to_ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def _overlap_ms(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _assign(
    start_ms: int, end_ms: int, turns: list[SpeakerTurn]
) -> tuple[str | None, AlignmentQuality]:
    duration = max(1, end_ms - start_ms)
    overlaps: dict[str, int] = {}
    for turn in turns:
        t_start, t_end = _to_ms(turn.start_seconds), _to_ms(turn.end_seconds)
        ov = _overlap_ms(start_ms, end_ms, t_start, t_end)
        if ov > 0:
            overlaps[turn.speaker_label] = overlaps.get(turn.speaker_label, 0) + ov

    if not overlaps:
        return None, AlignmentQuality.UNASSIGNED

    if len(overlaps) > 1:
        # Multiple distinct speakers active during this span — honestly
        # flag as overlap rather than silently picking the larger one.
        dominant_label = max(overlaps, key=lambda k: overlaps[k])
        return dominant_label, AlignmentQuality.OVERLAP

    (dominant_label, dominant_ov) = next(iter(overlaps.items()))
    ratio = dominant_ov / duration
    quality = (
        AlignmentQuality.CONFIDENT if ratio >= CONFIDENT_THRESHOLD else AlignmentQuality.AMBIGUOUS
    )
    return dominant_label, quality


def _worst(qualities: list[AlignmentQuality]) -> AlignmentQuality:
    return max(qualities, key=lambda q: _QUALITY_PRIORITY[q])


def _align_segment_word_level(
    segment: TranscriptSegment, turns: list[SpeakerTurn]
) -> list[AlignedSegment]:
    aligned_words: list[AlignedWord] = []
    for w in segment.words:
        w_start, w_end = _to_ms(w.start_seconds), _to_ms(w.end_seconds)
        label, quality = _assign(w_start, w_end, turns)
        aligned_words.append(
            AlignedWord(
                text=w.text,
                start_ms=w_start,
                end_ms=w_end,
                confidence=w.confidence,
                speaker_label=label,
                quality=quality,
            )
        )

    if not aligned_words:
        return []

    groups: list[list[AlignedWord]] = []
    current: list[AlignedWord] = [aligned_words[0]]
    for w in aligned_words[1:]:
        if w.speaker_label == current[-1].speaker_label:
            current.append(w)
        else:
            groups.append(current)
            current = [w]
    groups.append(current)

    results: list[AlignedSegment] = []
    for group in groups:
        text = " ".join(w.text for w in group).strip()
        confidences = [w.confidence for w in group if w.confidence is not None]
        results.append(
            AlignedSegment(
                start_ms=group[0].start_ms,
                end_ms=group[-1].end_ms,
                text=text,
                confidence=(sum(confidences) / len(confidences)) if confidences else None,
                speaker_label=group[0].speaker_label,
                quality=_worst([w.quality for w in group]),
                words=group,
            )
        )
    return results


def _align_segment_no_words(
    segment: TranscriptSegment, turns: list[SpeakerTurn]
) -> list[AlignedSegment]:
    start_ms, end_ms = _to_ms(segment.start_seconds), _to_ms(segment.end_seconds)
    label, quality = _assign(start_ms, end_ms, turns)
    return [
        AlignedSegment(
            start_ms=start_ms,
            end_ms=end_ms,
            text=segment.text,
            confidence=segment.confidence,
            speaker_label=label,
            quality=quality,
            words=[],
        )
    ]


def align_transcript(
    transcription: TranscriptionResult, diarization: DiarizationResult | None
) -> list[AlignedSegment]:
    """The one entry point app.processing calls after STT (+ optional
    diarization) both complete. Never mutates its inputs."""
    turns = list(diarization.turns) if diarization is not None else []

    output: list[AlignedSegment] = []
    for segment in transcription.segments:
        if not turns:
            output.extend(_align_segment_no_words(segment, turns))
            continue
        if segment.words:
            output.extend(_align_segment_word_level(segment, turns))
        else:
            output.extend(_align_segment_no_words(segment, turns))
    return output
