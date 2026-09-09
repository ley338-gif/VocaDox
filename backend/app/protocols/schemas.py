"""Pydantic validation schema for one LLM protocol-generation response —
the JSON shape `app.providers.llm.LLMProvider.complete_structured` is
constrained to and validated against (never trusted un-validated, same
discipline as every Phase 4 extraction category schema in
`app.intelligence.schemas`).

Every section/item optionally cites `source_segment_sequences` — the
transcript segment numbers (the same "SEG n" numbering
`app.transcription.rendering.render_transcript` puts in the prompt) that
support it. `app.protocols.service.run_protocol_generation` resolves
these against real segments and silently drops any that don't resolve —
this schema only shapes *what the model is allowed to claim*, not
whether that claim is trusted.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SECTION_TYPES = (
    "introduction",
    "topic",
    "facts",
    "discussion",
    "decision",
    "action_items",
    "open_questions",
    "note",
    "conclusion",
)

ITEM_TYPES = ("important_point", "decision", "action_item", "open_question", "fact", "note")


class GeneratedProtocolItem(BaseModel):
    item_type: str = Field(description=f"One of: {', '.join(ITEM_TYPES)}")
    text: str
    responsible_label: str | None = Field(
        default=None,
        description="Who is responsible, using their exact speaker label if stated -- only "
        "meaningful for item_type='action_item'. Omit if not stated.",
    )
    due_date: str | None = Field(
        default=None, description="Due date/timeframe exactly as stated, if any."
    )
    source_segment_sequences: list[int] = Field(default_factory=list)


class GeneratedProtocolSection(BaseModel):
    section_type: str = Field(description=f"One of: {', '.join(SECTION_TYPES)}")
    title: str = Field(description="A short, specific title for this section, in the language "
        "of the transcript -- never a generic placeholder like 'Section 1'.")
    summary: str = Field(description="A concise prose summary of this section, 1-3 sentences.")
    items: list[GeneratedProtocolItem] = Field(default_factory=list)
    source_segment_sequences: list[int] = Field(
        default_factory=list,
        description="Segment numbers spanning this whole section, used to derive its start/end "
        "timestamp -- include every segment covered by this section, not just the first/last.",
    )


class ProtocolGenerationResult(BaseModel):
    sections: list[GeneratedProtocolSection] = Field(default_factory=list)
