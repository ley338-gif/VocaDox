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

from typing import Literal, get_args

from pydantic import BaseModel, Field

SectionType = Literal[
    "introduction", "topic", "facts", "discussion", "decision", "action_items",
    "open_questions", "note", "conclusion"
]
ItemType = Literal["important_point", "decision", "action_item", "open_question", "fact", "note"]

SECTION_TYPES = get_args(SectionType)
ITEM_TYPES = get_args(ItemType)


class GeneratedProtocolItem(BaseModel):
    item_type: ItemType = Field(description=f"One of: {', '.join(ITEM_TYPES)}")
    text: str = Field(min_length=1, max_length=5000)
    responsible_label: str | None = Field(
        default=None, max_length=255,
        description="Who is responsible, using their exact speaker label if stated -- only "
        "meaningful for item_type='action_item'. Omit if not stated.",
    )
    due_date: str | None = Field(
        default=None, max_length=64, description="Due date/timeframe exactly as stated, if any."
    )
    source_segment_sequences: list[int] = Field(min_length=1, max_length=500)


class GeneratedProtocolSection(BaseModel):
    section_type: SectionType = Field(description=f"One of: {', '.join(SECTION_TYPES)}")
    title: str = Field(min_length=1, max_length=255, description="A short, specific title for "
        "this section, in the language of the transcript -- never a generic placeholder like "
        "'Section 1'.")
    summary: str = Field(min_length=1, max_length=5000,
        description="A concise prose summary of this section, 1-3 sentences.")
    items: list[GeneratedProtocolItem] = Field(default_factory=list, max_length=100)
    source_segment_sequences: list[int] = Field(
        min_length=1, max_length=500,
        description="Segment numbers spanning this whole section, used to derive its start/end "
        "timestamp -- include every segment covered by this section, not just the first/last.",
    )


class ProtocolGenerationResult(BaseModel):
    # An empty protocol is safer than forcing the model to invent content
    # when the transcript contains nothing it can ground.
    sections: list[GeneratedProtocolSection] = Field(default_factory=list, max_length=100)
