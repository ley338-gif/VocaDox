"""Follow-ups/Tasks: both AI_EXTRACTED (linked to a real originating
`extracted_facts` row) and USER_CREATED paths, plus organization-scoped
authorization (a task is exactly as reachable as its owning conversation)."""

from __future__ import annotations

import uuid

from app.intelligence.models import Certainty, ExtractedFact, FactStatus
from httpx import AsyncClient

from tests.longitudinal.conftest import login  # noqa: F401


async def test_ai_extracted_task_is_synced_from_existing_extracted_fact(
    client: AsyncClient, app_env, seeded  # noqa: ANN001
) -> None:
    app, sessionmaker = app_env
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]

    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Follow-up visit", "organization_id": org_a},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conversation_id = resp.json()["id"]

    async with sessionmaker() as session:
        fact = ExtractedFact(
            conversation_id=uuid.UUID(conversation_id),
            processing_run_id=None,
            category="task",
            fact_type="task",
            structured_value={
                "description": "Order follow-up blood test",
                "assignee": "Dr. Smith",
                "due_date": "in 2 weeks",
                "certainty": Certainty.STATED.value,
                "evidence_segment_sequences": [],
            },
            certainty=Certainty.STATED.value,
            confidence=None,
            status=FactStatus.UNVERIFIED.value,
        )
        session.add(fact)
        await session.commit()
        fact_id = fact.id

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/tasks", headers=headers)
    assert resp.status_code == 200, resp.text
    tasks = resp.json()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["source"] == "ai_extracted"
    assert task["source_fact_id"] == str(fact_id)
    assert task["description"] == "Order follow-up blood test"
    assert task["assignee"] == "Dr. Smith"
    assert task["due_date"] == "in 2 weeks"
    assert task["status"] == "open"

    # Calling the list endpoint again must NOT duplicate the synced task
    # (idempotent sync — matched by source_fact_id).
    resp2 = await client.get(f"/api/v1/conversations/{conversation_id}/tasks", headers=headers)
    assert len(resp2.json()) == 1


async def test_user_created_task_full_lifecycle(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]

    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Meeting", "organization_id": org_a},
        headers=headers,
    )
    conversation_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/tasks",
        json={"description": "Send meeting notes to Person A", "assignee": "Person A"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["source"] == "user_created"
    assert task["source_fact_id"] is None
    assert task["status"] == "open"

    resp = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "done"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/tasks", headers=headers)
    assert resp.json()[0]["status"] == "done"


async def test_task_endpoints_require_permission_and_are_org_scoped(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    org_a = seeded["org_a"]

    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Alice's conversation", "organization_id": org_a},
        headers=alice_headers,
    )
    conversation_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/tasks",
        json={"description": "Alice's task"},
        headers=alice_headers,
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]

    bob_headers = await login(client, "bob", "another very strong pw 456")
    # Bob (Org B) cannot list Alice's conversation's tasks.
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/tasks", headers=bob_headers)
    assert resp.status_code == 404, resp.text

    # Bob cannot create a task on Alice's conversation either.
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/tasks",
        json={"description": "Bob shouldn't be able to add this"},
        headers=bob_headers,
    )
    assert resp.status_code == 404, resp.text

    # Bob cannot update Alice's task by guessing its UUID.
    resp = await client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "dismissed"}, headers=bob_headers
    )
    assert resp.status_code == 404, resp.text


async def test_update_task_rejects_invalid_status(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "X", "organization_id": org_a},
        headers=headers,
    )
    conversation_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/tasks",
        json={"description": "Task"},
        headers=headers,
    )
    task_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "not_a_real_status"}, headers=headers
    )
    assert resp.status_code == 422, resp.text


async def test_list_tasks_is_cross_conversation_and_org_scoped(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    """GET /tasks (the org-wide "Aufgaben" list) must return tasks across
    every one of the caller's own conversations, and never another
    organization's tasks — same isolation rule as every other cross-
    conversation listing in this project."""
    alice_headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]

    conv1 = await client.post(
        "/api/v1/conversations",
        json={"title": "Visit 1", "organization_id": org_a},
        headers=alice_headers,
    )
    conv2 = await client.post(
        "/api/v1/conversations",
        json={"title": "Visit 2", "organization_id": org_a},
        headers=alice_headers,
    )
    for conv, description in ((conv1, "Task from visit 1"), (conv2, "Task from visit 2")):
        resp = await client.post(
            f"/api/v1/conversations/{conv.json()['id']}/tasks",
            json={"description": description},
            headers=alice_headers,
        )
        assert resp.status_code == 201, resp.text

    resp = await client.get("/api/v1/tasks", headers=alice_headers)
    assert resp.status_code == 200, resp.text
    descriptions = {t["description"] for t in resp.json()}
    assert descriptions == {"Task from visit 1", "Task from visit 2"}

    bob_headers = await login(client, "bob", "another very strong pw 456")
    bob_resp = await client.get("/api/v1/tasks", headers=bob_headers)
    assert bob_resp.status_code == 200
    assert bob_resp.json() == []
