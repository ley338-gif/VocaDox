"""Admin Portal Retention Policy CRUD — the `retention_policies` data
model has existed since Phase 2 with no admin UI/API until now. No
automated enforcement scheduler here (Phase 11 scope) — this is
management of the policy rows only."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_retention_write_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/retention-policies",
        json={"name": "Test Policy", "retention_days": 30},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_retention_policy_crud_lifecycle(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    create_resp = await client.post(
        "/api/v1/admin/retention-policies",
        json={
            "name": "Standard 90 days",
            "retention_days": 90,
            "delete_source_media": True,
            "delete_derived_media": False,
            "active": True,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    policy = create_resp.json()
    assert policy["retention_days"] == 90
    assert policy["active"] is True

    list_resp = await client.get("/api/v1/admin/retention-policies", headers=headers)
    assert list_resp.status_code == 200
    assert any(p["id"] == policy["id"] for p in list_resp.json())

    update_resp = await client.patch(
        f"/api/v1/admin/retention-policies/{policy['id']}",
        json={"retention_days": 180, "active": False},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["retention_days"] == 180
    assert updated["active"] is False
    # Fields not included in the PATCH body are left untouched.
    assert updated["delete_source_media"] is True


async def test_retention_read_only_role_cannot_write(client, seeded) -> None:  # noqa: ANN001
    """The standard "User" role (bob) has neither retention:read nor
    retention:write — retention policy administration is Manager/System
    Admin only."""
    headers = await login(client, "bob", "another very strong pw 456")
    resp = await client.get("/api/v1/admin/retention-policies", headers=headers)
    assert resp.status_code == 403
