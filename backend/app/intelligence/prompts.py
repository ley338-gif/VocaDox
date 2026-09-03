"""Prompt construction for structured extraction. Deliberately narrow —
one prompt per category (see app.intelligence.schemas.EXTRACTION_CATEGORIES),
never one giant "read this whole conversation and write a report" prompt
(spec §23/§24).

Never logs the rendered prompt text or transcript content (spec §63) —
only this module and app.intelligence.service ever see it in memory.
"""

from __future__ import annotations

from app.intelligence.schemas import NOT_MENTIONED

SYSTEM_PROMPT = (
    "You are a structured information extraction system. You extract only facts that are "
    "explicitly present in the given transcript. You NEVER invent, infer beyond what is "
    "stated, or guess a plausible-sounding value. If a requested field is not stated in the "
    f"transcript, you MUST use exactly the string '{NOT_MENTIONED}' for that field instead of "
    "guessing. Every extracted item must include the transcript segment number(s) (the "
    "integer after 'SEG' in the transcript) that support it in 'evidence_segment_sequences'. "
    "If you cannot point to a specific segment, return an empty list for "
    "'evidence_segment_sequences' rather than guessing a segment number."
)

_CATEGORY_INSTRUCTIONS: dict[str, str] = {
    "general_fact": (
        "Extract general facts stated in the transcript as subject/attribute/value triples "
        "(e.g. subject='Ramipril', attribute='dose', value='5mg'; or subject='Termin', "
        "attribute='date', value='Montag 10 Uhr'). Only extract facts that are explicitly "
        "and unambiguously stated. Do not extract opinions or small talk."
    ),
    "decision": (
        "Extract concrete decisions that were made during the conversation (not proposals or "
        "open questions). For each decision, note who decided it if stated, otherwise "
        f"'{NOT_MENTIONED}'."
    ),
    "task": (
        "Extract concrete tasks, action items, or follow-ups that someone is expected to do "
        "after this conversation. For each, note who is responsible (assignee) and when it is "
        f"due, using '{NOT_MENTIONED}' for either field if not stated."
    ),
}


def render_transcript(segments: list[tuple[int, str]]) -> str:
    """`segments` is a list of (sequence, text) tuples in order. Renders
    each as a `[SEG n] text` line so the model can cite sequence numbers
    back — the only mechanism by which evidence gets linked (see
    app.intelligence.schemas' module docstring)."""
    return "\n".join(f"[SEG {seq}] {text}" for seq, text in segments)


def build_prompt(category: str, transcript_text: str) -> str:
    instructions = _CATEGORY_INSTRUCTIONS[category]
    return (
        f"{instructions}\n\n"
        "Transcript (each line is one segment, tagged with its segment number):\n"
        f"{transcript_text}\n\n"
        "Return only facts genuinely present above. Respond with JSON matching the given "
        "schema."
    )
