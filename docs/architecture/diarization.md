# Diarization

## Provenance chain

`NormalizedMedia` → `ProcessingRun` (`run_type=DIARIZATION`) →
`DetectedSpeaker` (one per distinct voice cluster) + `DiarizationSegment`
(one per turn). See `app/diarization/models.py` and
`app/diarization/service.py`.

## Normalized result contract

`app/providers/diarization.py`'s `DiarizationResult`:

```python
DiarizationResult(
    turns=[SpeakerTurn(start_seconds, end_seconds, speaker_label, confidence)],
    speaker_count,
)
```

Provider-specific labels are normalized into generic `SPEAKER_00`-style
strings here — nothing pyannote-specific leaks past this boundary.

## DetectedSpeaker vs. ConversationParticipant

Deliberately separate concepts:
- **`DetectedSpeaker`** — a diarization-run-scoped, machine-detected voice
  cluster. No identity, no biometrics, scoped to one run.
- **`ConversationParticipant`** (Phase 2) — a human-entered participant
  record.

Mapping one to the other (`DetectedSpeaker.participant_id`/
`display_label`) is always an explicit human action via `PATCH
/conversations/{id}/speakers/{speaker_id}` — never automatic, never a
voice-biometric match. See `app/diarization/router.py`.

## Overlap handling

`persist_diarization_result` marks a `DiarizationSegment.is_overlap=true`
whenever its time range intersects another turn's range — diarization
output legitimately contains simultaneous speech, and VocaDox represents
that honestly rather than assuming one-speaker-at-a-time. The alignment
stage (`docs/architecture/alignment.md`) turns overlapping coverage of a
word/segment into an explicit `OVERLAP` quality flag.

## Speaker count hints

`min_speakers`/`max_speakers` are optional, per-request hints (never a
global default) — see `docs/admin/diarization-provider.md`.

## Confidence

pyannote's default pipeline doesn't expose a genuine per-turn confidence
score; `SpeakerTurn.confidence` is documented as an honest `1.0`
placeholder in that case rather than a fabricated calibrated value (see
`app/providers/diarization.py`'s `PyannoteDiarizationProvider.diarize`
docstring comment). Don't compare this value across providers as if it
were a universal probability.
