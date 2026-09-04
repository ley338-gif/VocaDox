"""Admin Portal Audit viewer: lists/filters real accumulated `audit_events`
rows without exposing prohibited content — gated by the pre-existing
`audit:read` permission (System Admin, Manager, Auditor)."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_audit_events_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/audit-events", headers=headers)
    assert resp.status_code == 403


async def test_audit_events_lists_real_login_events(client, seeded) -> None:  # noqa: ANN001
    # alice's own login below is itself a real event to be listed.
    await login(client, "alice", "a very strong password 123")
    carol_headers = await login(client, "carol", "yet another strong pw 789")

    resp = await client.get("/api/v1/admin/audit-events", headers=carol_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 2  # alice's login + carol's own login
    event_types = {e["event_type"] for e in body["items"]}
    assert "login" in event_types

    filtered = await client.get(
        "/api/v1/admin/audit-events",
        params={"username": "alice", "event_type": "login"},
        headers=carol_headers,
    )
    assert filtered.status_code == 200
    assert all(e["username"] == "alice" for e in filtered.json()["items"])

    # Hard rule: no event ever carries conversation/fact/transcript/
    # document content — only small structured metadata (ids, field
    # names), verified here on every event this test actually produced.
    for event in body["items"]:
        metadata = event["event_metadata"] or {}
        assert "content" not in metadata
        assert "text" not in metadata

    types_resp = await client.get("/api/v1/admin/audit-events/event-types", headers=carol_headers)
    assert types_resp.status_code == 200
    assert "login" in types_resp.json()["event_types"]
