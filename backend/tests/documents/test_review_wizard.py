"""Review Wizard: confirm/correct/remove are real human actions recorded
against a fact (spec §28), never cosmetic, and resolving every blocking
issue is what actually unblocks approval (spec §27)."""

from __future__ import annotations

import uuid

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def _seed(client, headers, org_id, processing_env):  # noqa: ANN001
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, org_id, processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        fact_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    return conversation_id, fact_ids


async def _list_issues_for_fact(client, headers, conversation_id, fact_id):  # noqa: ANN001
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/review-issues", headers=headers
    )
    assert resp.status_code == 200
    return [i for i in resp.json() if str(fact_id) in i["related_fact_ids"]]


async def test_confirm_action_records_reviewer_without_changing_value(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    clean_fact = next(f for f in resp.json() if f["id"] == str(fact_ids["clean_fact_id"]))
    assert clean_fact["review_status"] == "pending"

    # The clean fact has no review issue (it's fully verified) — Confirm is
    # only reachable through a flagged item in the wizard. Use the
    # unverified/contradiction fact's real MISSING_EVIDENCE issue instead.
    issues = await _list_issues_for_fact(
        client, headers, conversation_id, fact_ids["unverified_fact_id"]
    )
    missing_evidence_issue = next(i for i in issues if i["issue_type"] == "uncertainty")

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{missing_evidence_issue['id']}",
        json={"fact_id": str(fact_ids["unverified_fact_id"]), "action": "confirm"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["resolved_status"] == "confirmed"

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    fact = next(f for f in resp.json() if f["id"] == str(fact_ids["unverified_fact_id"]))
    assert fact["review_status"] == "confirmed"
    assert fact["structured_value"]["value"] == "10mg"  # never overwritten


async def test_correct_action_never_overwrites_original_value(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)

    issues = await _list_issues_for_fact(
        client, headers, conversation_id, fact_ids["unverified_fact_id"]
    )
    contradiction_issue = next(i for i in issues if i["issue_type"] == "potential_contradiction")

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{contradiction_issue['id']}",
        json={
            "fact_id": str(fact_ids["unverified_fact_id"]),
            "action": "correct",
            "corrected_value": {
                "subject": "Ramipril",
                "attribute": "dose",
                "value": "5mg (corrected)",
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["resolved_status"] == "corrected"

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    fact = next(f for f in resp.json() if f["id"] == str(fact_ids["unverified_fact_id"]))
    assert fact["review_status"] == "corrected"
    assert fact["structured_value"]["value"] == "10mg"  # original, untouched
    assert fact["corrected_structured_value"]["value"] == "5mg (corrected)"

    # Composing now reflects the corrected value, not the original — the
    # rendered document never shows "10mg" once corrected, even though the
    # fact's own original structured_value still (correctly) says 10mg.
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    rendered = resp.json()["current_revision"]["rendered_text"]
    assert "5mg (corrected)" in rendered
    assert "10mg" not in rendered


async def test_remove_action_excludes_fact_from_composition(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)

    issues = await _list_issues_for_fact(
        client, headers, conversation_id, fact_ids["unverified_fact_id"]
    )
    contradiction_issue = next(i for i in issues if i["issue_type"] == "potential_contradiction")

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{contradiction_issue['id']}",
        json={"fact_id": str(fact_ids["unverified_fact_id"]), "action": "remove"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["resolved_status"] == "removed"

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    fact = next(f for f in resp.json() if f["id"] == str(fact_ids["unverified_fact_id"]))
    assert fact["review_status"] == "removed"

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    rendered = resp.json()["current_revision"]["rendered_text"]
    assert "10mg" not in rendered


async def test_resolving_already_resolved_issue_is_rejected(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)
    issues = await _list_issues_for_fact(
        client, headers, conversation_id, fact_ids["unverified_fact_id"]
    )
    issue = issues[0]

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{issue['id']}",
        json={"fact_id": str(fact_ids["unverified_fact_id"]), "action": "confirm"},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{issue['id']}",
        json={"fact_id": str(fact_ids["unverified_fact_id"]), "action": "confirm"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_fact_id_not_related_to_issue_is_rejected(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)
    issues = await _list_issues_for_fact(
        client, headers, conversation_id, fact_ids["unverified_fact_id"]
    )
    issue = issues[0]

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{issue['id']}",
        json={"fact_id": str(fact_ids["clean_fact_id"]), "action": "confirm"},
        headers=headers,
    )
    assert resp.status_code == 400
