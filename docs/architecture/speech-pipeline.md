# Speech-to-text pipeline

## Provenance chain

`SourceMedia` (immutable, Phase 2) → `NormalizedMedia` (a new
`MediaAsset`, `kind=NORMALIZED_AUDIO`) → `ProcessingRun`
(`run_type=SPEECH_TO_TEXT`) → `Transcript` + `TranscriptSegment` rows.
Every segment retains `speech_run_id` — you can always trace a piece of
transcript text back to exactly which provider/model/config produced it.

## Normalized result contract

`app/providers/speech_to_text.py`'s `TranscriptionResult` is the one
internal shape every speech provider (real or fake) must produce:

```python
TranscriptionResult(
    segments=[
        TranscriptSegment(start_seconds, end_seconds, text, confidence,
                           words=(Word(text, start_seconds, end_seconds, confidence), ...))
    ],
    language, language_confidence, duration_ms,
)
```

Provider-specific values (faster-whisper's internal beam-search state,
VAD parameters, etc.) never leak past this boundary into domain code —
what's worth keeping for provenance lives in
`ProcessingRun.configuration_snapshot` instead (device, compute_type,
beam_size, vad_enabled, language_hint).

## Stages (see app/processing/orchestrator.py)

1. **NORMALIZE** — `FfmpegMediaNormalizer` (or the Phase 2
   `NoOpMediaNormalizer` fallback) converts source audio to mono 16kHz PCM
   WAV. Idempotent: keyed on `source_media_id + normalizer_version +
   normalization_profile`.
2. **TRANSCRIBE** — the speech provider runs against the normalized
   audio; raw output is stored on the `ProcessingRun.raw_output` JSON
   column (isolated, not yet persisted as `TranscriptSegment` rows — see
   below).
3. **ALIGN** — combines this run's output with any diarization run's
   output (see `docs/architecture/alignment.md`) and is the **only**
   writer of `TranscriptSegment` rows.

## Why raw ASR output isn't persisted as segments immediately

If `TRANSCRIBE` persisted `TranscriptSegment` rows directly and `ALIGN`
later re-wrote them once diarization also finished, a user could
theoretically start correcting a segment in the narrow window between the
two — and have their correction silently clobbered. Storing the raw
result on the `ProcessingRun` and letting `ALIGN` be the sole
`TranscriptSegment` writer avoids that race entirely; segments only ever
exist once alignment has already run.

## VAD

`vad_filter` (faster-whisper's built-in Silero VAD) is configuration-
driven (`FasterWhisperConfig.vad_filter`, default `true`) and recorded in
`ProcessingRun.configuration_snapshot` — VocaDox never silently drops
audio regions without provenance of that decision.

## Silence

Long silent stretches simply don't produce ASR segments — no placeholder
"[silence]" rows are invented. The source audio remains fully seekable
regardless; only the transcript is sparse where there was nothing to
transcribe.
