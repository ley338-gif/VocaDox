"""KnownSpeaker CRUD, organization isolation, and participant linkage."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login


async def _create_conversation(client: AsyncClient, headers: dict, org_id: str) -> dict:
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Visit 1", "organization_id": org_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_list_update_delete_known_speaker(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]

    create_response = await client.post(
        f"/api/v1/known-speakers?organization_id={org_id}",
        json={"display_name": "Yvonne", "notes": "Praxisleitung"},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    known_speaker = create_response.json()
    assert known_speaker["display_name"] == "Yvonne"
    assert known_speaker["organization_id"] == org_id

    list_response = await client.get(
        f"/api/v1/known-speakers?organization_id={org_id}", headers=headers
    )
    assert list_response.status_code == 200
    assert [k["display_name"] for k in list_response.json()] == ["Yvonne"]

    update_response = await client.patch(
        f"/api/v1/known-speakers/{known_speaker['id']}",
        json={"display_name": "Yvonne M."},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Yvonne M."

    delete_response = await client.delete(
        f"/api/v1/known-speakers/{known_speaker['id']}", headers=headers
    )
    assert delete_response.status_code == 204

    list_after_delete = await client.get(
        f"/api/v1/known-speakers?organization_id={org_id}", headers=headers
    )
    assert list_after_delete.json() == []


async def test_cross_organization_known_speaker_isolation(
    client: AsyncClient, seeded: dict
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]
    create_response = await client.post(
        f"/api/v1/known-speakers?organization_id={org_a}",
        json={"display_name": "Yvonne"},
        headers=alice_headers,
    )
    assert create_response.status_code == 201

    bob_headers = await login(client, "bob", "another very strong pw 456")
    list_response = await client.get(
        f"/api/v1/known-speakers?organization_id={org_a}", headers=bob_headers
    )
    assert list_response.status_code == 403

    update_response = await client.patch(
        f"/api/v1/known-speakers/{create_response.json()['id']}",
        json={"display_name": "hijacked"},
        headers=bob_headers,
    )
    assert update_response.status_code == 403


async def test_participant_links_to_known_speaker(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]

    known_speaker = (
        await client.post(
            f"/api/v1/known-speakers?organization_id={org_id}",
            json={"display_name": "Yvonne"},
            headers=headers,
        )
    ).json()

    conv = await _create_conversation(client, headers, org_id)
    participant_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/participants",
        json={"display_name": "Yvonne", "known_speaker_id": known_speaker["id"]},
        headers=headers,
    )
    assert participant_response.status_code == 201
    assert participant_response.json()["known_speaker_id"] == known_speaker["id"]

    # A second conversation's participant can link (or unlink) to the same
    # known speaker independently — the identity is org-wide, the
    # participant row stays per-conversation.
    conv2 = await _create_conversation(client, headers, org_id)
    participant2_response = await client.post(
        f"/api/v1/conversations/{conv2['id']}/participants",
        json={"display_name": "Yvonne"},
        headers=headers,
    )
    participant2_id = participant2_response.json()["id"]
    assert participant2_response.json()["known_speaker_id"] is None

    link_response = await client.patch(
        f"/api/v1/conversations/{conv2['id']}/participants/{participant2_id}",
        json={"known_speaker_id": known_speaker["id"]},
        headers=headers,
    )
    assert link_response.status_code == 200
    assert link_response.json()["known_speaker_id"] == known_speaker["id"]
