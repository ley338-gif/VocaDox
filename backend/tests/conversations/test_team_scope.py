"""Team-scoped conversation/task visibility (post-GA): a conversation may
optionally belong to a Group ("team", reusing the existing Group model —
see app.conversations.authz's module docstring). Mirrors the existing
cross-organization isolation tests in test_api.py, but isolates the team
dimension from the organization dimension using the `team_seeded` fixture
(alice and dave are both in org_a but different teams)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login


async def _create_conversation(
    client: AsyncClient,
    headers: dict,
    org_id: str,
    *,
    title: str = "Team meeting",
    group_id: str | None = None,
) -> dict:
    payload = {"title": title, "organization_id": org_id}
    if group_id is not None:
        payload["group_id"] = group_id
    response = await client.post("/api/v1/conversations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_team_a_member_gets_404_on_team_b_conversation(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(
        client, dave_headers, seeded["org_a"], group_id=team_seeded["team_b_id"]
    )

    alice_headers = await login(client, "alice", "a very strong password 123")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=alice_headers)
    assert response.status_code == 404  # never 403 — same posture as cross-org isolation


async def test_system_admin_bypasses_team_scope(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(
        client, dave_headers, seeded["org_a"], group_id=team_seeded["team_b_id"]
    )

    carol_headers = await login(client, "carol", "yet another strong pw 789")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=carol_headers)
    assert response.status_code == 200


async def test_manager_role_bypasses_team_scope(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(
        client, dave_headers, seeded["org_a"], group_id=team_seeded["team_b_id"]
    )

    erin_headers = await login(client, "erin", "a fourth very strong pw 111")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=erin_headers)
    assert response.status_code == 200


async def test_conversation_with_no_team_visible_to_whole_org(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    """Regression guard for the "existing data" decision: a conversation
    with no group_id must stay visible to every org member regardless of
    team, exactly like every pre-team-scoping conversation."""
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(client, dave_headers, seeded["org_a"])
    assert conv["group_id"] is None

    alice_headers = await login(client, "alice", "a very strong password 123")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=alice_headers)
    assert response.status_code == 200


async def test_cannot_create_conversation_in_team_youre_not_a_member_of(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    response = await client.post(
        "/api/v1/conversations",
        json={
            "title": "Sneaky",
            "organization_id": seeded["org_a"],
            "group_id": team_seeded["team_b_id"],
        },
        headers=alice_headers,
    )
    assert response.status_code == 403


async def test_list_conversations_excludes_other_teams(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(
        client,
        dave_headers,
        seeded["org_a"],
        title="Team B only",
        group_id=team_seeded["team_b_id"],
    )

    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/conversations", headers=alice_headers)
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()["items"]}
    assert conv["id"] not in ids

    erin_headers = await login(client, "erin", "a fourth very strong pw 111")
    resp = await client.get("/api/v1/conversations", headers=erin_headers)
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()["items"]}
    assert conv["id"] in ids


async def test_org_wide_tasks_endpoint_respects_team_scope(
    client: AsyncClient, seeded: dict, team_seeded: dict
) -> None:
    dave_headers = await login(client, "dave", "a third very strong pw 000")
    conv = await _create_conversation(
        client, dave_headers, seeded["org_a"], group_id=team_seeded["team_b_id"]
    )
    task_resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/tasks",
        json={"description": "Team B's task"},
        headers=dave_headers,
    )
    assert task_resp.status_code == 201, task_resp.text

    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/tasks", headers=alice_headers)
    assert resp.status_code == 200
    assert "Team B's task" not in {t["description"] for t in resp.json()}

    erin_headers = await login(client, "erin", "a fourth very strong pw 111")
    resp = await client.get("/api/v1/tasks", headers=erin_headers)
    assert resp.status_code == 200
    assert "Team B's task" in {t["description"] for t in resp.json()}
