# 0022 — Deterministic word-overlap alignment algorithm

## Status
Accepted

## Context
ASR output (text + timing) and diarization output (speaker + timing) are
produced independently by two different providers/models and must be
combined into a single speaker-attributed transcript. The brief requires
a deterministic algorithm, word-level overlap assignment where word
timestamps exist, segment-splitting at speaker changes, preserved ASR
timing/provenance, and an honest per-segment quality flag — "never
silently assign a speaker on weak temporal evidence."

## Decision
Implemented in `app/transcription/alignment.py` (pure functions, no I/O,
no DB — see its module docstring for the full algorithm description).
Summary:

1. No diarization result (or zero turns) -> the whole ASR segment becomes
   one output segment, `speaker_label=None`, `quality=UNASSIGNED`.
2. ASR segment has word timestamps -> **word-level path**: for each word,
   compute millisecond overlap against every diarization turn.
   - No overlapping turn -> word is `UNASSIGNED`.
   - More than one distinct speaker label overlaps the word -> word is
     `OVERLAP` (multiple people were talking during this word's span —
     represented honestly, never collapsed to whichever speaker "won").
   - Exactly one speaker overlaps, `overlap_ms / word_duration_ms >= 0.66`
     -> `CONFIDENT`; below that threshold -> `AMBIGUOUS` (weak temporal
     evidence, still assigned but flagged for review, never silently
     upgraded).
   - Consecutive words are grouped by assigned speaker label — this is
     the "split transcript segments when speaker changes mid-ASR-segment"
     requirement. Each group's quality is the *worst* quality among its
     words (`OVERLAP > AMBIGUOUS > UNASSIGNED > CONFIDENT`), since a
     single weak/ambiguous word means the whole resulting segment needs
     review, not just that one word.
3. ASR segment has no word timestamps -> **segment-level fallback**:
   identical overlap logic applied to the segment's own `[start, end]`
   range as a single unit. Cannot split without word timing — documented
   limitation, not a silent gap (exercised by
   `test_word_timing_unavailable_falls_back_to_segment_level`).

`CONFIDENT_THRESHOLD = 0.66` is a deliberately conservative, documented
constant (not "hidden inside a magic number") — a word needs clear
temporal dominance by one speaker before VocaDox claims confidence in the
attribution.

## Alternatives considered
- **Segment-level-only alignment** (ignore word timestamps entirely):
  simpler, but loses the ability to split an ASR segment at a genuine
  mid-sentence speaker change, which is common in real conversation audio
  and was explicitly called out in the brief as a required test case.
- **Majority-vote without an ambiguity threshold** (always assign the
  dominant speaker regardless of margin): rejected — this is exactly the
  "silently assign a speaker on weak temporal evidence" the brief
  prohibits; a 51/49 split would be indistinguishable from a 99/1 split
  in the transcript UI without the `AMBIGUOUS` flag.
- **A learned/ML aligner**: out of scope for this phase (adds another
  model/license surface for marginal benefit over deterministic temporal
  overlap on typically-non-overlapping conversational turns).

## Consequences
- Unit-tested in isolation (`tests/transcription/test_alignment.py`, 9
  tests) covering every case named in the brief: clean single speaker,
  speaker change mid-segment, equal overlap, no diarization coverage,
  diarization overlap, word timing unavailable, boundary-exactly-equal,
  plus a non-mutation guarantee (the function never mutates its inputs).
- `TranscriptSegment.alignment_quality` and `.review_flag` are the direct
  outputs of this algorithm's per-segment quality — this is exactly the
  Phase 3 "Low-confidence review foundation" data, with no LLM/clinical
  judgement involved.
- Because the algorithm is pure and DB-free, it can be re-run against
  archived `ProcessingRun.raw_output` (the stored normalized ASR/
  diarization results) if the algorithm itself is later improved,
  without re-invoking either provider.
