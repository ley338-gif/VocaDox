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
    "'evidence_segment_sequences' rather than guessing a segment number. All extracted text "
    "values (e.g. subject, attribute, value, decision text, task description) MUST be written "
    "in the same language the transcript itself is spoken in — never translate them to "
    "English or any other language, regardless of the language of this instruction."
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


def get_builtin_category_instruction(category: str) -> str:
    """Public accessor for `_CATEGORY_INSTRUCTIONS`, used by
    `app.templates.schema_builder` when a template's category definition
    marks itself `builtin: true` (i.e. the "General Conversation"
    template) so it can reuse the exact wording rather than duplicating
    it."""
    return _CATEGORY_INSTRUCTIONS[category]


def render_transcript(segments: list[tuple[int, str]]) -> str:
    """`segments` is a list of (sequence, text) tuples in order. Renders
    each as a `[SEG n] text` line so the model can cite sequence numbers
    back — the only mechanism by which evidence gets linked (see
    app.intelligence.schemas' module docstring)."""
    return "\n".join(f"[SEG {seq}] {text}" for seq, text in segments)


def build_prompt(category: str, transcript_text: str) -> str:
    return build_prompt_from_instruction(_CATEGORY_INSTRUCTIONS[category], transcript_text)


def build_prompt_from_instruction(instruction: str, transcript_text: str) -> str:
    """Phase 6: the template-driven counterpart of `build_prompt` — takes
    the instruction text directly (from a `TemplateVersion`'s category
    definition or an admin-published `PromptVersion`) instead of looking it
    up by a fixed category key, so a template-defined category (e.g.
    Meeting's "agenda_topic") gets a real, category-specific prompt too,
    not a generic fallback."""
    return (
        f"{instruction}\n\n"
        "Transcript (each line is one segment, tagged with its segment number):\n"
        f"{transcript_text}\n\n"
        "Return only facts genuinely present above. Respond with JSON matching the given "
        "schema."
    )
