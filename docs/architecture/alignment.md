# Alignment

See `docs/architecture/adr/0022-alignment-algorithm.md` for the accepted
decision and rationale; this document is the practical reference.

## Purpose

Combine independently-produced ASR output (text + timing) and diarization
output (speaker + timing) into one speaker-attributed transcript, without
ever silently guessing a speaker on weak evidence.

## Algorithm summary

Implemented in `app/transcription/alignment.py` (pure functions, unit
tested in isolation in `tests/transcription/test_alignment.py`):

1. No diarization coverage at all -> `speaker_label=None`, quality
   `UNASSIGNED`.
2. Word timestamps available -> **word-level overlap**: for each word,
   find the diarization turn(s) overlapping its time range in
   milliseconds.
   - No overlap -> `UNASSIGNED`.
   - More than one distinct speaker overlaps -> `OVERLAP`.
   - One speaker, overlap ratio ≥ 0.66 of the word's duration ->
     `CONFIDENT`.
   - One speaker, overlap ratio < 0.66 -> `AMBIGUOUS`.
   Consecutive words with the same assigned speaker are grouped into one
   output segment — this is how an original ASR segment gets **split**
   exactly where the speaker changes mid-sentence. A segment's quality is
   the worst quality among its words.
3. No word timestamps -> the same overlap logic applied to the whole
   segment as a single unit (can't split without word timing).

## Quality flags become review data

Every `TranscriptSegment.alignment_quality` value feeds directly into
`review_flag`/`review_flag_reason` (`app/transcription/service.py`'s
`_review_flag`) — this is the mechanical mixture of "low ASR confidence,"
"no diarization," "ambiguous," and "overlap" signals the Transcript UI
shows as **⚠ prüfen**. There is no LLM or clinical-importance scoring
here (that's explicitly out of scope for Phase 3).

## Timing preservation

Alignment never changes original ASR word/segment start/end times — it
only decides how to group and label them. `TranscriptSegment.start_ms`/
`end_ms` for a word-level-split segment are exactly the first and last
word's original timestamps.

## Known limitations

- The 0.66 confidence threshold is a fixed, documented constant — not
  learned or tunable per-deployment in Phase 3.
- A segment with no word timestamps can't be split even if diarization
  shows a speaker change partway through it — the whole segment gets one
  speaker/quality decision (`test_word_timing_unavailable_falls_back_to_segment_level`).
- No cross-provider confidence calibration is attempted — see
  `docs/architecture/diarization.md`'s note on confidence semantics.
