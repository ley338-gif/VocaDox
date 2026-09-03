"""Structured extraction schemas (spec §23/§24): narrow, well-defined
Pydantic models per category — never one unconstrained "write a report"
prompt. Each category schema doubles as the JSON Schema handed to the LLM
provider's structured-output mode (`.model_json_schema()`) AND as the
validator the raw LLM response is checked against — the same contract on
both ends, so "the model returned something that doesn't fit the schema"
is a real, catchable validation error, never silently coerced.

Every item carries `evidence_segment_sequences`: the transcript segment
sequence number(s) (from the `[SEG n]`-tagged prompt, see
app.intelligence.prompts) the model claims support it. This is the only
mechanism by which a fact gets linked to real evidence — a sequence
number that doesn't resolve to a real segment of the transcript being
extracted is *never* trusted (see app.intelligence.service), so the LLM
cannot fabricate evidence, only fail to provide any (-> UNVERIFIED).

`certainty` mirrors app.intelligence.models.Certainty. The LLM is
explicitly instructed (see app.intelligence.prompts) to use `NOT_MENTIONED`
for a field it cannot find rather than inventing a plausible value —
verified against a real model in PHASE_4_VALIDATION_REPORT.md.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Certainty(StrEnum):
    STATED = "stated"
    UNCLEAR = "unclear"
    INCOMPLETE = "incomplete"
    NOT_MENTIONED = "not_mentioned"


NOT_MENTIONED = "NOT_MENTIONED"


class GeneralFactItem(BaseModel):
    """A domain-neutral subject/attribute/value triple — e.g. subject=
    "Ramipril", attribute="dose", value="5mg" (the spec's own example),
    or subject="Termin", attribute="date", value="Montag 10 Uhr". This
    shape is what makes contradiction detection possible generically (see
    app.intelligence.contradictions): two GENERAL_FACT items in the same
    conversation with the same normalized (subject, attribute) but a
    different value are a real, structural contradiction, not a fuzzy
    text-similarity guess."""

    subject: str = Field(max_length=256)
    attribute: str = Field(max_length=128)
    value: str = Field(max_length=1024)
    certainty: Certainty
    evidence_segment_sequences: list[int] = Field(default_factory=list)


class GeneralFactsExtraction(BaseModel):
    facts: list[GeneralFactItem] = Field(default_factory=list)


class DecisionItem(BaseModel):
    description: str = Field(max_length=1024)
    decided_by: str = Field(max_length=256, description=f"Person/role, or '{NOT_MENTIONED}'.")
    certainty: Certainty
    evidence_segment_sequences: list[int] = Field(default_factory=list)


class DecisionsExtraction(BaseModel):
    decisions: list[DecisionItem] = Field(default_factory=list)


class TaskItem(BaseModel):
    """Covers both "Tasks" and "Follow-Ups" from the spec's example
    category list — a follow-up is modeled as a task with a due_date and
    no completed-work implied, a deliberate simplification documented in
    docs/architecture/intelligence-pipeline.md rather than adding a
    fourth near-identical schema."""

    description: str = Field(max_length=1024)
    assignee: str = Field(max_length=256, description=f"Person/role, or '{NOT_MENTIONED}'.")
    due_date: str = Field(max_length=128, description=f"Date/time phrase, or '{NOT_MENTIONED}'.")
    certainty: Certainty
    evidence_segment_sequences: list[int] = Field(default_factory=list)


class TasksExtraction(BaseModel):
    tasks: list[TaskItem] = Field(default_factory=list)


# category name -> (wrapper schema, item field name, fact_type)
EXTRACTION_CATEGORIES: dict[str, tuple[type[BaseModel], str, str]] = {
    "general_fact": (GeneralFactsExtraction, "facts", "general_fact"),
    "decision": (DecisionsExtraction, "decisions", "decision"),
    "task": (TasksExtraction, "tasks", "task"),
}
