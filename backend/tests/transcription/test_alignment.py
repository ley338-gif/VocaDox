"""Unit tests for the deterministic alignment algorithm
(app.transcription.alignment), covering every case the spec calls out
explicitly: clean single speaker, speaker change mid-ASR-segment, equal
overlap, no diarization coverage, diarization overlap, word timing
unavailable, boundary exactly equal. No DB, no provider I/O — pure
function tests.
"""

from __future__ import annotations

from app.providers.diarization import DiarizationResult, SpeakerTurn
from app.providers.speech_to_text import TranscriptionResult, TranscriptSegment, Word
from app.transcription.alignment import AlignmentQuality, align_transcript


def _seg(start, end, text, words=(), confidence=0.95) -> TranscriptSegment:
    return TranscriptSegment(start, end, text, confidence, words=words)


def test_clean_single_speaker() -> None:
    transcription = TranscriptionResult(
        segments=[
            _seg(
                0.0,
                2.0,
                "hello there",
                words=(Word("hello", 0.0, 1.0, 0.9), Word("there", 1.0, 2.0, 0.9)),
            )
        ],
        language="en",
    )
    diarization = DiarizationResult(turns=[SpeakerTurn(0.0, 2.0, "SPEAKER_00")], speaker_count=1)

    result = align_transcript(transcription, diarization)

    assert len(result) == 1
    assert result[0].speaker_label == "SPEAKER_00"
    assert result[0].quality == AlignmentQuality.CONFIDENT
    assert result[0].text == "hello there"


def test_speaker_change_mid_segment_splits_the_segment() -> None:
    transcription = TranscriptionResult(
        segments=[
            _seg(
                0.0,
                4.0,
                "hello there general kenobi",
                words=(
                    Word("hello", 0.0, 1.0, 0.9),
                    Word("there", 1.0, 2.0, 0.9),
                    Word("general", 2.0, 3.0, 0.9),
                    Word("kenobi", 3.0, 4.0, 0.9),
                ),
            )
        ],
        language="en",
    )
    diarization = DiarizationResult(
        turns=[SpeakerTurn(0.0, 2.0, "SPEAKER_00"), SpeakerTurn(2.0, 4.0, "SPEAKER_01")],
        speaker_count=2,
    )

    result = align_transcript(transcription, diarization)

    assert len(result) == 2
    assert result[0].speaker_label == "SPEAKER_00"
    assert result[0].text == "hello there"
    assert result[1].speaker_label == "SPEAKER_01"
    assert result[1].text == "general kenobi"
    assert all(r.quality == AlignmentQuality.CONFIDENT for r in result)
    # Original ASR timing preserved on each side of the split.
    assert result[0].start_ms == 0 and result[0].end_ms == 2000
    assert result[1].start_ms == 2000 and result[1].end_ms == 4000


def test_equal_overlap_between_two_speakers_is_ambiguous_not_confident() -> None:
    # A single word spans exactly two turns 50/50 — neither dominates, so
    # this must never be silently marked CONFIDENT.
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 2.0, "word", words=(Word("word", 0.0, 2.0, 0.9),))],
        language="en",
    )
    diarization = DiarizationResult(
        turns=[SpeakerTurn(0.0, 1.0, "SPEAKER_00"), SpeakerTurn(1.0, 2.0, "SPEAKER_01")],
        speaker_count=2,
    )

    result = align_transcript(transcription, diarization)

    assert len(result) == 1
    # Both turns overlap the single word -> multiple distinct speakers ->
    # honestly flagged OVERLAP (not silently assigned to one or the other).
    assert result[0].quality == AlignmentQuality.OVERLAP


def test_no_diarization_coverage_is_unassigned_not_guessed() -> None:
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 2.0, "hello", words=(Word("hello", 0.0, 2.0, 0.9),))],
        language="en",
    )

    result = align_transcript(transcription, diarization=None)

    assert len(result) == 1
    assert result[0].speaker_label is None
    assert result[0].quality == AlignmentQuality.UNASSIGNED


def test_diarization_present_but_no_turns_overlap_this_word_is_unassigned() -> None:
    transcription = TranscriptionResult(
        segments=[_seg(10.0, 12.0, "hello", words=(Word("hello", 10.0, 12.0, 0.9),))],
        language="en",
    )
    diarization = DiarizationResult(turns=[SpeakerTurn(0.0, 2.0, "SPEAKER_00")], speaker_count=1)

    result = align_transcript(transcription, diarization)

    assert result[0].speaker_label is None
    assert result[0].quality == AlignmentQuality.UNASSIGNED


def test_overlapping_speech_is_flagged_not_silently_assigned() -> None:
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 3.0, "hello there", words=(Word("hello there", 0.0, 3.0, 0.9),))],
        language="en",
    )
    # Two speakers talk simultaneously across the whole word span.
    diarization = DiarizationResult(
        turns=[SpeakerTurn(0.0, 3.0, "SPEAKER_00"), SpeakerTurn(0.0, 3.0, "SPEAKER_01")],
        speaker_count=2,
    )

    result = align_transcript(transcription, diarization)

    assert result[0].quality == AlignmentQuality.OVERLAP
    assert result[0].speaker_label in {"SPEAKER_00", "SPEAKER_01"}


def test_word_timing_unavailable_falls_back_to_segment_level() -> None:
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 2.0, "hello there", words=())],  # no word timestamps
        language="en",
    )
    diarization = DiarizationResult(turns=[SpeakerTurn(0.0, 2.0, "SPEAKER_00")], speaker_count=1)

    result = align_transcript(transcription, diarization)

    assert len(result) == 1
    assert result[0].speaker_label == "SPEAKER_00"
    assert result[0].quality == AlignmentQuality.CONFIDENT
    assert result[0].words == []


def test_boundary_exactly_equal_between_word_and_turn() -> None:
    # Word ends exactly where the turn ends; overlap arithmetic must not
    # double count or drop this boundary case.
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 1.0, "hi", words=(Word("hi", 0.0, 1.0, 0.9),))],
        language="en",
    )
    diarization = DiarizationResult(turns=[SpeakerTurn(0.0, 1.0, "SPEAKER_00")], speaker_count=1)

    result = align_transcript(transcription, diarization)

    assert result[0].speaker_label == "SPEAKER_00"
    assert result[0].quality == AlignmentQuality.CONFIDENT
    assert result[0].start_ms == 0
    assert result[0].end_ms == 1000


def test_alignment_never_mutates_inputs() -> None:
    transcription = TranscriptionResult(
        segments=[_seg(0.0, 1.0, "hi", words=(Word("hi", 0.0, 1.0, 0.9),))], language="en"
    )
    diarization = DiarizationResult(turns=[SpeakerTurn(0.0, 1.0, "SPEAKER_00")], speaker_count=1)
    snapshot_segments = list(transcription.segments)
    snapshot_turns = list(diarization.turns)

    align_transcript(transcription, diarization)

    assert transcription.segments == snapshot_segments
    assert diarization.turns == snapshot_turns
