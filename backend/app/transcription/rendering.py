"""Speaker-labeled transcript rendering for an LLM prompt — shared by
`app.intelligence.service` (structured fact extraction) and
`app.protocols.service` (protocol generation), both of which need exactly
the same "what did this transcript actually say, and who said it" text
sent to a model. Extracted from `app.intelligence.service` (which owned
this first, Phase 4) rather than duplicated, once a second caller needed
it (Post-GA Protokoll).

Never logs the rendered text or transcript content (spec §63) — only the
caller (already under the same discipline) ever sees it in memory.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diarization.models import DetectedSpeaker
from app.transcription.models import TranscriptSegment


async def load_speaker_labels(
    session: AsyncSession, speaker_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Resolves each `DetectedSpeaker.id` to the same `display_label ??
    internal_label` a human reviewer already sees (see
    app.diarization.service/the transcript UI's `SpeakerBadge`) — including
    a real participant name once one has been assigned (`SpeakerAssignRow`
    sets `display_label` to the participant's `display_name` on
    assignment), so a prompt tells the model the same identity a human
    would use, never a separate/invented one."""
    if not speaker_ids:
        return {}
    result = await session.execute(
        select(DetectedSpeaker).where(DetectedSpeaker.id.in_(speaker_ids))
    )
    return {s.id: s.display_label or s.internal_label for s in result.scalars().all()}


def segment_text(segment: TranscriptSegment) -> str:
    return segment.corrected_text or segment.original_text


def segment_line(segment: TranscriptSegment, speaker_labels: dict[uuid.UUID, str]) -> str:
    """Prefixes the segment's text with its speaker's label when one is
    resolvable, e.g. `[Dr. Müller] ...` — the only mechanism by which a
    prompt learns who said what; a segment with no `speaker_id` (no
    diarization run, or a single-speaker conversation) renders exactly as
    before, unprefixed."""
    text = segment_text(segment)
    label = speaker_labels.get(segment.speaker_id) if segment.speaker_id else None
    return f"[{label}] {text}" if label else text


def render_transcript(segments: list[tuple[int, str]]) -> str:
    """`segments` is a list of (sequence, text) tuples in order. Renders
    each as a `[SEG n] text` line so the model can cite sequence numbers
    back — the only mechanism by which a generated statement gets linked
    to real evidence."""
    return "\n".join(f"[SEG {seq}] {text}" for seq, text in segments)


def build_transcript_text(
    segments: list[TranscriptSegment],
    speaker_labels: dict[uuid.UUID, str],
    *,
    max_chars: int,
) -> str:
    """Renders `segments` as speaker-labeled `[SEG n] ...` lines, truncated
    (oldest-first kept, most recent dropped) if the result would exceed
    `max_chars` — a real, honest limitation surfaced by the caller
    choosing its own cap, never a silent full-transcript send that risks
    a provider-side context overflow with no visible error."""
    pairs = [(s.sequence, segment_line(s, speaker_labels)) for s in segments]
    text = render_transcript(pairs)
    if len(text) <= max_chars:
        return text
    truncated_pairs: list[tuple[int, str]] = []
    total = 0
    for seq, seg_text in pairs:
        line_len = len(seg_text) + 10
        if total + line_len > max_chars:
            break
        truncated_pairs.append((seq, seg_text))
        total += line_len
    return render_transcript(truncated_pairs)
