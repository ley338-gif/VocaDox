"""Post-GA P1-3: template completeness score — category coverage,
decision/task owner completeness, and speaking-share/longest-monologue
metrics from diarization.
"""

from __future__ import annotations

import uuid

from app.intelligence.models import Certainty, ExtractedFact, FactStatus
from httpx import AsyncClient

from tests.completeness.conftest import login  # noqa: F401
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


async def test_completeness_with_no_facts_is_fully_uncovered(
    client: AsyncClient, app_env, seeded  # noqa: ANN001
) -> None:
    _, _ = app_env
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Empty conversation", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conversation_id = resp.json()["id"]

    completeness = await client.get(
        f"/api/v1/conversations/{conversation_id}/completeness", headers=headers
    )
    assert completeness.status_code == 200, completeness.text
    body = completeness.json()
    assert body["template_key"] == "general"
    assert {c["category"] for c in body["categories"]} == {"general_fact", "decision", "task"}
    assert all(not c["covered"] for c in body["categories"])
    assert body["category_coverage_ratio"] == 0.0
    assert body["decisions_total"] == 0
    assert body["tasks_total"] == 0
    # No decisions/tasks exist yet, so only the category-coverage signal
    # applies -- overall_score equals it exactly, not penalized twice.
    assert body["overall_score"] == 0.0
    assert body["speaking_shares"] == []
    assert body["longest_monologue"] is None


async def test_completeness_reflects_missing_decision_and_task_owners(
    client: AsyncClient, app_env, seeded  # noqa: ANN001
) -> None:
    app, sessionmaker = app_env
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Team sync", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    conversation_id = resp.json()["id"]

    def _fact(category: str, structured_value: dict) -> ExtractedFact:
        return ExtractedFact(
            conversation_id=uuid.UUID(conversation_id),
            processing_run_id=None,
            category=category,
            fact_type=category,
            structured_value=structured_value,
            certainty=Certainty.STATED.value,
            confidence=None,
            status=FactStatus.UNVERIFIED.value,
        )

    async with sessionmaker() as session:
        session.add_all(
            [
                _fact(
                    "general_fact",
                    {
                        "subject": "Budget",
                        "attribute": "amount",
                        "value": "5000 EUR",
                        "certainty": Certainty.STATED.value,
                        "evidence_segment_sequences": [],
                    },
                ),
                _fact(
                    "decision",
                    {
                        "description": "Adopt new vendor",
                        "decided_by": "Team lead",
                        "certainty": Certainty.STATED.value,
                        "evidence_segment_sequences": [],
                    },
                ),
                _fact(
                    "decision",
                    {
                        "description": "Postpone launch",
                        "decided_by": "NOT_MENTIONED",
                        "certainty": Certainty.UNCLEAR.value,
                        "evidence_segment_sequences": [],
                    },
                ),
                _fact(
                    "task",
                    {
                        "description": "Send invoice",
                        "assignee": "Finance",
                        "due_date": "NOT_MENTIONED",
                        "certainty": Certainty.STATED.value,
                        "evidence_segment_sequences": [],
                    },
                ),
                _fact(
                    "task",
                    {
                        "description": "Follow up with client",
                        "assignee": "NOT_MENTIONED",
                        "due_date": "NOT_MENTIONED",
                        "certainty": Certainty.UNCLEAR.value,
                        "evidence_segment_sequences": [],
                    },
                ),
            ]
        )
        await session.commit()

    completeness = await client.get(
        f"/api/v1/conversations/{conversation_id}/completeness", headers=headers
    )
    assert completeness.status_code == 200, completeness.text
    body = completeness.json()
    assert all(c["covered"] for c in body["categories"])
    assert body["category_coverage_ratio"] == 1.0
    assert body["decisions_total"] == 2
    assert body["decisions_missing_decided_by"] == 1
    assert body["tasks_total"] == 2
    assert body["tasks_missing_assignee"] == 1
    # mean(category=1.0, decisions=0.5, tasks=0.5)
    assert body["overall_score"] == 2 / 3


async def test_completeness_speaking_metrics_from_diarization(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text
    await run_all_jobs(sessionmaker, queue, storage)

    completeness = await client.get(
        f"/api/v1/conversations/{conversation_id}/completeness", headers=headers
    )
    assert completeness.status_code == 200, completeness.text
    body = completeness.json()

    # FakeDiarizationProvider always reports two equal-length 2.5s turns.
    assert len(body["speaking_shares"]) == 2
    for share in body["speaking_shares"]:
        assert share["speaking_ms"] == 2500
        assert share["share"] == 0.5

    assert body["longest_monologue"] is not None
    assert body["longest_monologue"]["duration_ms"] == 2500
    assert body["longest_monologue"]["label"] == "SPEAKER_00"
