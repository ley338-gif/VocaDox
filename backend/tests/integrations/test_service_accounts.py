"""Real end-to-end tests for Service Accounts (Phase 10, spec §54):
create -> secret shown exactly once -> real API-key-authenticated call
against the REST Integration API -> scope enforcement (both "no such
scope" and "wrong organization") -> rotation invalidates the old key ->
revocation rejects the revoked key. No mocking of the auth path -- every
call here is a real HTTP request through the real FastAPI app.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login


async def _create_service_account(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    organization_id: str,
    scopes: list[str],
    owner_user_id: str,
    name: str = "integration-tester",
) -> dict:
    response = await client.post(
        "/api/v1/admin/service-accounts",
        json={
            "name": name,
            "organization_id": organization_id,
            "scopes": scopes,
            "owner_user_id": owner_user_id,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_shows_key_once_and_list_never_returns_secret(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read"],
        owner_user_id=seeded["alice_id"],
    )
    assert "api_key" in created and created["api_key"].startswith("sa_")
    assert created["key_prefix"] in created["api_key"]

    listed = await client.get("/api/v1/admin/service-accounts", headers=admin_headers)
    assert listed.status_code == 200
    for row in listed.json():
        assert "api_key" not in row
        assert "secret_hash" not in row


async def test_real_api_key_authenticates_scoped_request(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read", "conversation:create"],
        owner_user_id=seeded["alice_id"],
    )
    api_key = created["api_key"]

    resp = await client.post(
        "/api/v1/integrations/api/conversations",
        json={"title": "SA-created conversation", "organization_id": seeded["org_a"]},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201, resp.text
    conversation = resp.json()
    assert conversation["organization_id"] == seeded["org_a"]

    listed = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert listed.status_code == 200
    assert any(c["id"] == conversation["id"] for c in listed.json())
    return conversation["id"]


async def test_out_of_scope_permission_is_denied(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read"],  # no conversation:create
        owner_user_id=seeded["alice_id"],
    )
    api_key = created["api_key"]

    resp = await client.post(
        "/api/v1/integrations/api/conversations",
        json={"title": "should be denied", "organization_id": seeded["org_a"]},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 403, resp.text


async def test_cross_organization_resource_is_denied(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    org_a_account = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read", "conversation:create"],
        owner_user_id=seeded["alice_id"],
        name="org-a-sa",
    )
    create_resp = await client.post(
        "/api/v1/integrations/api/conversations",
        json={"title": "org A only", "organization_id": seeded["org_a"]},
        headers={"Authorization": f"Bearer {org_a_account['api_key']}"},
    )
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["id"]

    org_b_account = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_b"],
        scopes=["conversation:read"],
        owner_user_id=seeded["bob_id"],
        name="org-b-sa",
    )
    cross_org_resp = await client.get(
        f"/api/v1/integrations/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {org_b_account['api_key']}"},
    )
    assert cross_org_resp.status_code == 404, cross_org_resp.text


async def test_invalid_and_missing_api_key_are_rejected(client, seeded):
    resp = await client.get("/api/v1/integrations/api/conversations")
    assert resp.status_code == 401

    resp = await client.get(
        "/api/v1/integrations/api/conversations",
        headers={"Authorization": "Bearer sa_deadbeef.not-a-real-secret"},
    )
    assert resp.status_code == 401


async def test_rotation_invalidates_old_key_and_new_key_works(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read"],
        owner_user_id=seeded["alice_id"],
    )
    old_key = created["api_key"]
    account_id = created["id"]

    old_key_check = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {old_key}"}
    )
    assert old_key_check.status_code == 200

    rotate_resp = await client.post(
        f"/api/v1/admin/service-accounts/{account_id}/rotate", headers=admin_headers
    )
    assert rotate_resp.status_code == 200, rotate_resp.text
    new_key = rotate_resp.json()["api_key"]
    assert new_key != old_key

    old_key_after_rotation = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {old_key}"}
    )
    assert old_key_after_rotation.status_code == 401

    new_key_works = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {new_key}"}
    )
    assert new_key_works.status_code == 200


async def test_revocation_rejects_the_key_immediately(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read"],
        owner_user_id=seeded["alice_id"],
    )
    api_key = created["api_key"]
    account_id = created["id"]

    before = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert before.status_code == 200

    revoke_resp = await client.post(
        f"/api/v1/admin/service-accounts/{account_id}/revoke", headers=admin_headers
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["is_active"] is False

    after = await client.get(
        "/api/v1/integrations/api/conversations", headers={"Authorization": f"Bearer {api_key}"}
    )
    assert after.status_code == 401


async def test_create_rejects_unknown_scope(client, seeded):
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/service-accounts",
        json={
            "name": "bad-scopes",
            "organization_id": seeded["org_a"],
            "scopes": ["totally:madeup"],
            "owner_user_id": seeded["alice_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_non_admin_cannot_manage_service_accounts(client, seeded):
    user_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/service-accounts",
        json={
            "name": "alice-should-not-be-able-to-do-this",
            "organization_id": seeded["org_a"],
            "scopes": ["conversation:read"],
            "owner_user_id": seeded["alice_id"],
        },
        headers=user_headers,
    )
    assert resp.status_code == 403
