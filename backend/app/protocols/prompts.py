"""Prompt construction for Protokoll generation — one structured call over
the whole transcript (unlike `app.intelligence.prompts`' one-call-per-
category extraction, a protocol's sections are inherently sequential/
interdependent, so splitting this into multiple calls would need a real
multi-stage pipeline this codebase doesn't have yet — see
docs/architecture/adr/0042-protokoll.md).

Never logs the rendered prompt text or transcript content (spec §63) —
only this module and app.protocols.service ever see it in memory.
"""

from __future__ import annotations

from app.protocols.schemas import ITEM_TYPES, SECTION_TYPES

SYSTEM_PROMPT = (
    "You are a structured meeting/consultation protocol generator. You read a transcript and "
    "produce a chronological sequence of sections that together summarize what was discussed, "
    "decided, and what happens next -- never a verbatim transcript, never inventing content not "
    "actually present.\n\n"
    "Ground rules:\n"
    "- Only summarize what is explicitly stated. Never invent facts, decisions, or names.\n"
    "- Every section, and every item within it, MUST include the transcript segment number(s) "
    "(the integer after 'SEG') that support it, in 'source_segment_sequences'. If you cannot "
    "point to specific segments, use an empty list rather than guessing.\n"
    "- Some transcript lines are prefixed with the speaker who said them, e.g. '[Dr. Müller] "
    "...'. When noting who is responsible for an action item, use that EXACT bracketed label "
    "verbatim -- never invent a name, never construct a placeholder referencing a segment "
    "number.\n"
    "- Sections must be in chronological order, matching the order things were actually "
    "discussed.\n"
    f"- section_type must be one of: {', '.join(SECTION_TYPES)}.\n"
    f"- item_type must be one of: {', '.join(ITEM_TYPES)}.\n"
    "- Choose section titles and section/item ordering that genuinely fit THIS conversation -- "
    "do not force a fixed template of sections onto every conversation. A short conversation "
    "may need only 2-3 sections; a long one may need many. Only include an 'action_items' or "
    "'open_questions' section if the conversation actually contains any.\n"
    "- All generated text (titles, summaries, item text) MUST be written in the same language "
    "the transcript itself is spoken in -- never translate to English or any other language, "
    "regardless of the language of this instruction."
)


def build_prompt(transcript_text: str) -> str:
    return (
        "Read the following transcript and produce a structured protocol as described.\n\n"
        "Transcript (each line is one segment, tagged with its segment number):\n"
        f"{transcript_text}\n\n"
        "Respond with JSON matching the given schema. Reminder: every text value in your JSON "
        "output MUST be written in the same language as the transcript above."
    )
