"""JSON (de)serialization for the normalized provider-result dataclasses,
used only to round-trip a `ProcessingRun.raw_output` value between the
worker execution that produced it and the later ALIGN stage that consumes
it. Kept separate from the dataclasses themselves (app.providers.*) since
this is persistence plumbing, not provider-contract shape.
"""

from __future__ import annotations

from typing import Any

from app.providers.diarization import DiarizationResult, SpeakerTurn
from app.providers.speech_to_text import TranscriptionResult, TranscriptSegment, Word


def transcription_result_to_dict(result: TranscriptionResult) -> dict[str, Any]:
    return {
        "language": result.language,
        "language_confidence": result.language_confidence,
        "duration_ms": result.duration_ms,
        "segments": [
            {
                "start_seconds": s.start_seconds,
                "end_seconds": s.end_seconds,
                "text": s.text,
                "confidence": s.confidence,
                "provider_segment_id": s.provider_segment_id,
                "words": [
                    {
                        "text": w.text,
                        "start_seconds": w.start_seconds,
                        "end_seconds": w.end_seconds,
                        "confidence": w.confidence,
                    }
                    for w in s.words
                ],
            }
            for s in result.segments
        ],
    }


def transcription_result_from_dict(data: dict[str, Any]) -> TranscriptionResult:
    segments = [
        TranscriptSegment(
            start_seconds=s["start_seconds"],
            end_seconds=s["end_seconds"],
            text=s["text"],
            confidence=s["confidence"],
            words=tuple(
                Word(
                    text=w["text"],
                    start_seconds=w["start_seconds"],
                    end_seconds=w["end_seconds"],
                    confidence=w["confidence"],
                )
                for w in s.get("words", [])
            ),
            provider_segment_id=s.get("provider_segment_id"),
        )
        for s in data["segments"]
    ]
    return TranscriptionResult(
        segments=segments,
        language=data["language"],
        language_confidence=data.get("language_confidence"),
        duration_ms=data.get("duration_ms"),
    )


def diarization_result_to_dict(result: DiarizationResult) -> dict[str, Any]:
    return {
        "speaker_count": result.speaker_count,
        "turns": [
            {
                "start_seconds": t.start_seconds,
                "end_seconds": t.end_seconds,
                "speaker_label": t.speaker_label,
                "confidence": t.confidence,
            }
            for t in result.turns
        ],
    }


def diarization_result_from_dict(data: dict[str, Any]) -> DiarizationResult:
    return DiarizationResult(
        turns=[
            SpeakerTurn(
                start_seconds=t["start_seconds"],
                end_seconds=t["end_seconds"],
                speaker_label=t["speaker_label"],
                confidence=t.get("confidence", 1.0),
            )
            for t in data["turns"]
        ],
        speaker_count=data["speaker_count"],
    )
