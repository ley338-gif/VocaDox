from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login


async def test_user_only_sees_own_organizations(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    response = await client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200
    org_ids = {org["id"] for org in response.json()}
    assert org_ids == {seeded["org_a"]}


async def test_admin_sees_all_organizations(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    response = await client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200
    org_ids = {org["id"] for org in response.json()}
    assert org_ids == {seeded["org_a"], seeded["org_b"]}


async def test_organizations_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/organizations")
    assert response.status_code == 401
