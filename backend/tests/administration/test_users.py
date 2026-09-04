"""Admin Portal Users surface: list/view/create/deactivate over the exact
Phase 1 RBAC model — no parallel permission system, gated by the
pre-existing `user:manage` permission."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_list_users_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_create_view_deactivate_user_lifecycle(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    create_resp = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "dave",
            "password": "a brand new strong password",
            "display_name": "Dave",
            "email": "dave@example.test",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    user = create_resp.json()
    assert user["username"] == "dave"
    assert user["is_active"] is True
    assert user["group_ids"] == []

    list_resp = await client.get("/api/v1/admin/users", headers=headers)
    assert list_resp.status_code == 200
    assert any(u["username"] == "dave" for u in list_resp.json())

    get_resp = await client.get(f"/api/v1/admin/users/{user['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "dave@example.test"

    # Deactivation, not deletion — the user row still exists afterward.
    deactivate_resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}", json={"is_active": False}, headers=headers
    )
    assert deactivate_resp.status_code == 200, deactivate_resp.text
    assert deactivate_resp.json()["is_active"] is False

    still_listed = await client.get("/api/v1/admin/users", headers=headers)
    assert any(u["username"] == "dave" and u["is_active"] is False for u in still_listed.json())

    # A deactivated user can no longer log in.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dave", "password": "a brand new strong password"},
    )
    assert login_resp.status_code == 401


async def test_create_user_rejects_duplicate_username(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/users",
        json={"username": "alice", "password": "another strong password", "display_name": "Dup"},
        headers=headers,
    )
    assert resp.status_code == 409
