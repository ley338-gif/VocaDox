"""Ask VocaDox schemas (post-GA P1-1): the LLM-facing structured-output
contract (`AskLLMResponse`) and the public API request/response shapes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# -- LLM-facing structured output ---------------------------------------
#
# Deliberately mirrors app.intelligence.schemas' whole approach: the model
# must cite which given fact(s) support each statement it makes. Unlike
# extraction (where evidence is a transcript segment sequence number), here
# the "evidence" IS the already-extracted, already-evidence-linked fact
# itself -- the model picks from a closed list of real fact ids, it never
# invents one. Every statement is re-verified server-side after the call
# (app.ask.service._verify_statements) against the exact set of fact ids
# actually offered; this schema alone is not the enforcement, it only
# shapes what the model can express.


class AskLLMStatement(BaseModel):
    text: str = Field(max_length=1024)
    fact_ids: list[str] = Field(
        default_factory=list,
        description="ids from the numbered fact list above that support this statement",
    )


class AskLLMResponse(BaseModel):
    statements: list[AskLLMStatement] = Field(default_factory=list)


# -- Public API -----------------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: uuid.UUID | None = None


class AskCitation(BaseModel):
    fact_id: uuid.UUID
    conversation_id: uuid.UUID
    conversation_title: str
    category: str
    text: str


class AskStatementResponse(BaseModel):
    text: str
    citations: list[AskCitation]


class AskResponse(BaseModel):
    id: uuid.UUID
    question: str
    statements: list[AskStatementResponse]
    had_candidate_evidence: bool
    created_at: datetime
