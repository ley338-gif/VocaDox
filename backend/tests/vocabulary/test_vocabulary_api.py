"""Custom vocabulary CRUD, org isolation, permission enforcement, and
resolution precedence (post-GA P0-3)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login


async def test_create_list_update_delete_vocabulary(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    org_id = seeded["org_a"]

    create_response = await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={
            "name": "Org-weit",
            "terms": ["Ramipril", "Metoprolol"],
            "initial_prompt": "Arztgespräch.",
        },
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    entry = create_response.json()
    assert entry["name"] == "Org-weit"
    assert entry["terms"] == ["Ramipril", "Metoprolol"]
    assert entry["template_id"] is None

    list_response = await client.get(
        f"/api/v1/vocabulary?organization_id={org_id}", headers=headers
    )
    assert list_response.status_code == 200
    assert [e["name"] for e in list_response.json()] == ["Org-weit"]

    update_response = await client.patch(
        f"/api/v1/vocabulary/{entry['id']}?organization_id={org_id}",
        json={"terms": ["Ramipril", "Metoprolol", "Simvastatin"]},
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["terms"] == ["Ramipril", "Metoprolol", "Simvastatin"]

    delete_response = await client.delete(
        f"/api/v1/vocabulary/{entry['id']}?organization_id={org_id}", headers=headers
    )
    assert delete_response.status_code == 204

    list_after_delete = await client.get(
        f"/api/v1/vocabulary?organization_id={org_id}", headers=headers
    )
    assert list_after_delete.json() == []


async def test_duplicate_scope_is_rejected(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    org_id = seeded["org_a"]

    first = await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={"name": "A", "terms": ["x"]},
        headers=headers,
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={"name": "B", "terms": ["y"]},
        headers=headers,
    )
    assert second.status_code == 409, second.text


async def test_per_template_entry_takes_precedence_over_org_wide(
    client: AsyncClient, seeded: dict, app_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    org_id = seeded["org_a"]

    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    meeting_template_id = next(t["id"] for t in templates if t["key"] == "meeting")
    general_template_id = next(t["id"] for t in templates if t["key"] == "general")

    await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={"name": "Org-weit", "terms": ["Allgemeinbegriff"]},
        headers=headers,
    )
    await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={"name": "Meeting", "template_id": meeting_template_id, "terms": ["Sprintplanung"]},
        headers=headers,
    )

    from app.vocabulary.service import resolve_vocabulary

    _, sessionmaker = app_env
    async with sessionmaker() as session:
        import uuid as _uuid

        # A conversation whose effective template is Meeting gets the
        # more specific entry...
        meeting_resolved = await resolve_vocabulary(
            session,
            organization_id=_uuid.UUID(org_id),
            template_id=_uuid.UUID(meeting_template_id),
        )
        assert meeting_resolved is not None
        assert meeting_resolved.name == "Meeting"

        # ...while any other template falls back to the org-wide entry.
        general_resolved = await resolve_vocabulary(
            session,
            organization_id=_uuid.UUID(org_id),
            template_id=_uuid.UUID(general_template_id),
        )
        assert general_resolved is not None
        assert general_resolved.name == "Org-weit"


async def test_vocabulary_requires_organization_membership(
    client: AsyncClient, seeded: dict
) -> None:
    """Bob (Org B) must not read or manage Org A's vocabulary."""
    carol_headers = await login(client, "carol", "yet another strong pw 789")
    org_a = seeded["org_a"]
    create_response = await client.post(
        f"/api/v1/vocabulary?organization_id={org_a}",
        json={"name": "A", "terms": ["x"]},
        headers=carol_headers,
    )
    entry_id = create_response.json()["id"]

    bob_headers = await login(client, "bob", "another very strong pw 456")
    resp = await client.get(f"/api/v1/vocabulary?organization_id={org_a}", headers=bob_headers)
    assert resp.status_code == 403

    resp = await client.patch(
        f"/api/v1/vocabulary/{entry_id}?organization_id={org_a}",
        json={"name": "Hijacked"},
        headers=bob_headers,
    )
    assert resp.status_code == 403


async def test_vocabulary_requires_manage_permission(client: AsyncClient, seeded: dict) -> None:
    """Alice (User role) has vocabulary:read via known-speaker-adjacent
    grants only if explicitly listed -- User role is NOT granted
    vocabulary:manage, matching "verwaltet im Admin-Portal" (an admin/
    manager task, not every user's)."""
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]
    resp = await client.post(
        f"/api/v1/vocabulary?organization_id={org_id}",
        json={"name": "A", "terms": ["x"]},
        headers=headers,
    )
    assert resp.status_code == 403
