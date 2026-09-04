"""Phase 7 closes the pre-existing "organization creation has no HTTP
endpoint" gap flagged by the Phase 5/6 validation reports."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_create_organization_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "New Org", "slug": "new-org"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_create_organization_and_add_member(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    create_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "General Medicine", "slug": "general-medicine", "description": "GM dept"},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    org = create_resp.json()
    assert org["slug"] == "general-medicine"

    # Duplicate slug is rejected.
    dup_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Another name", "slug": "general-medicine"},
        headers=headers,
    )
    assert dup_resp.status_code == 409

    list_resp = await client.get("/api/v1/organizations", headers=headers)
    assert any(o["slug"] == "general-medicine" for o in list_resp.json())

    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")

    member_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": bob_id},
        headers=headers,
    )
    assert member_resp.status_code == 201, member_resp.text
    assert member_resp.json()["user_id"] == bob_id

    members_resp = await client.get(f"/api/v1/organizations/{org['id']}/members", headers=headers)
    assert members_resp.status_code == 200
    assert any(m["user_id"] == bob_id for m in members_resp.json())

    # Adding the same member twice is rejected, not silently duplicated.
    dup_member_resp = await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": bob_id},
        headers=headers,
    )
    assert dup_member_resp.status_code == 409
