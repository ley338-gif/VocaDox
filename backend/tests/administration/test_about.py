"""Admin Portal About & Licenses page."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_about_requires_system_admin(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/about", headers=headers)
    assert resp.status_code == 403


async def test_about_shows_application_version(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/about", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["application_version"]
    assert isinstance(body["license_summary"], dict)
    assert isinstance(body["third_party_notices_excerpt"], str)
