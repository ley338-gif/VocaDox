"""Admin Portal Groups surface: manage groups and their role assignments
over the exact Phase 1 RBAC model, gated by `group:manage`."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_list_groups_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/groups", headers=headers)
    assert resp.status_code == 403


async def test_create_group_assign_role_and_add_member(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    roles_resp = await client.get("/api/v1/admin/roles", headers=headers)
    assert roles_resp.status_code == 200
    reviewer_role = next(r for r in roles_resp.json() if r["name"] == "Reviewer")

    create_resp = await client.post(
        "/api/v1/admin/groups",
        json={
            "name": "Psychotherapy",
            "description": "Psychotherapy department",
            "role_ids": [reviewer_role["id"]],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    group = create_resp.json()
    assert group["role_ids"] == [reviewer_role["id"]]
    assert group["member_ids"] == []

    get_resp = await client.get(f"/api/v1/admin/groups/{group['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Psychotherapy"

    # Add alice as a member via the Users API's group_ids replacement.
    alice_resp = await client.get("/api/v1/admin/users", headers=headers)
    alice_id = next(u["id"] for u in alice_resp.json() if u["username"] == "alice")
    existing_groups_resp = await client.get(f"/api/v1/admin/users/{alice_id}", headers=headers)
    existing_group_ids = existing_groups_resp.json()["group_ids"]

    update_resp = await client.patch(
        f"/api/v1/admin/users/{alice_id}",
        json={"group_ids": [*existing_group_ids, group["id"]]},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert group["id"] in update_resp.json()["group_ids"]

    group_after = await client.get(f"/api/v1/admin/groups/{group['id']}", headers=headers)
    assert alice_id in group_after.json()["member_ids"]

    # Rename the group and replace its role grant.
    admin_role = next(r for r in roles_resp.json() if r["name"] == "System Admin")
    rename_resp = await client.patch(
        f"/api/v1/admin/groups/{group['id']}",
        json={"name": "Psychotherapy Dept", "role_ids": [admin_role["id"]]},
        headers=headers,
    )
    assert rename_resp.status_code == 200, rename_resp.text
    assert rename_resp.json()["name"] == "Psychotherapy Dept"
    assert rename_resp.json()["role_ids"] == [admin_role["id"]]
