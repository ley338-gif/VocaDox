"""Prompt for Recap generation — deliberately narrow: rewrite already-
composed, already-fact-checked Document content into a short,
plain-language narrative for the OTHER party. Never given the raw
transcript (see app.recap.service.generate_recap) — the source material
is always the deterministic Document's rendered_text, so the LLM has
nothing to hallucinate beyond what a human has already seen composed
from real extracted facts.

Never logs the rendered prompt text or its content (spec §63, same rule
as app.intelligence.prompts) — only this module and app.recap.service
ever see it in memory.
"""

from __future__ import annotations

from app.intelligence.schemas import NOT_MENTIONED

SYSTEM_PROMPT = (
    "You write a short, warm, plain-language recap of a conversation, addressed directly "
    "to the OTHER participant (e.g. a patient after-visit summary, or a recap for an "
    "external meeting attendee). You MUST base the recap ONLY on the structured notes "
    "given to you below — never invent, assume, or add any detail not present in them. "
    f"Never include internal annotations or the literal placeholder '{NOT_MENTIONED}' — "
    "simply omit anything not stated. Write in the SAME language the notes below are "
    "written in, never translate them. Keep it concise (a few short paragraphs), use plain "
    "prose (no headings, no bullet lists), and use a friendly, professional tone."
)


def build_prompt(document_text: str) -> str:
    return (
        "Structured notes from the conversation:\n\n"
        f"{document_text}\n\n"
        "Write the recap now."
    )
