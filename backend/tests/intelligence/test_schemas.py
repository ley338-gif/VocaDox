"""Schema validation: valid LLM output validates; invalid output raises a
real, catchable pydantic.ValidationError — never silently coerced."""

from __future__ import annotations

import pydantic
import pytest
from app.intelligence.schemas import (
    DecisionsExtraction,
    GeneralFactsExtraction,
    TasksExtraction,
)


def test_valid_general_fact_validates() -> None:
    payload = {
        "facts": [
            {
                "subject": "Ramipril",
                "attribute": "dose",
                "value": "5mg",
                "certainty": "stated",
                "evidence_segment_sequences": [3],
            }
        ]
    }
    validated = GeneralFactsExtraction.model_validate(payload)
    assert validated.facts[0].subject == "Ramipril"
    assert validated.facts[0].evidence_segment_sequences == [3]


def test_invalid_certainty_value_is_rejected() -> None:
    payload = {
        "facts": [
            {
                "subject": "Ramipril",
                "attribute": "dose",
                "value": "5mg",
                "certainty": "totally_sure",  # not a valid Certainty member
                "evidence_segment_sequences": [],
            }
        ]
    }
    with pytest.raises(pydantic.ValidationError):
        GeneralFactsExtraction.model_validate(payload)


def test_missing_required_field_is_rejected() -> None:
    payload = {"facts": [{"subject": "Ramipril", "certainty": "stated"}]}  # missing attribute/value
    with pytest.raises(pydantic.ValidationError):
        GeneralFactsExtraction.model_validate(payload)


def test_empty_extraction_is_valid() -> None:
    """The model finding nothing to extract is a legitimate, valid result —
    never an error."""
    assert GeneralFactsExtraction.model_validate({"facts": []}).facts == []
    assert DecisionsExtraction.model_validate({"decisions": []}).decisions == []
    assert TasksExtraction.model_validate({"tasks": []}).tasks == []


def test_decision_and_task_schemas_accept_not_mentioned() -> None:
    decision = DecisionsExtraction.model_validate(
        {
            "decisions": [
                {
                    "description": "Proceed with treatment plan",
                    "decided_by": "NOT_MENTIONED",
                    "certainty": "stated",
                    "evidence_segment_sequences": [1],
                }
            ]
        }
    )
    assert decision.decisions[0].decided_by == "NOT_MENTIONED"

    task = TasksExtraction.model_validate(
        {
            "tasks": [
                {
                    "description": "Send documents",
                    "assignee": "NOT_MENTIONED",
                    "due_date": "NOT_MENTIONED",
                    "certainty": "incomplete",
                    "evidence_segment_sequences": [],
                }
            ]
        }
    )
    assert task.tasks[0].assignee == "NOT_MENTIONED"
    assert task.tasks[0].certainty == "incomplete"
