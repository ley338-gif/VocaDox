"""New Integration API routes added for the GDT connector prototype
(ADR-0041): downloading export bytes via a service account (there was
previously no non-human-session way to do this at all) and creating a
participant via a service account with no `owner_user_id` configured
(participants, unlike conversations/documents, are never attributed to
a user -- this is a deliberate, pointed regression test for that
decision, not just a happy-path check).

Note on ordering: `client` is a single shared `httpx.AsyncClient` whose
cookie jar holds exactly one human session at a time -- logging in as a
second user overwrites the first user's active session cookie (their
CSRF token becomes stale for any *new* request, since the session it
was issued for is no longer the one attached to the client). Every test
below therefore does its admin (carol) session work first, then logs in
as the human user (alice) last, and only ever authenticates connector-
style calls via the service account's Bearer token afterward (which is
independent of the session cookie entirely)."""

from __future__ import annotations

import uuid

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)
from tests.integrations.test_service_accounts import _create_service_account


async def test_export_route_parity_with_human_route(client, seeded, processing_env) -> None:  # noqa: ANN001
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    service_account = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["document:read"],
        owner_user_id=seeded["alice_id"],
    )

    user_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, user_headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=user_headers
    )

    human_resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=gdt-text",
        headers=user_headers,
    )
    sa_resp = await client.get(
        f"/api/v1/integrations/api/conversations/{conversation_id}/document/export?format=gdt-text",
        headers={"Authorization": f"Bearer {service_account['api_key']}"},
    )
    assert human_resp.status_code == 200, human_resp.text
    assert sa_resp.status_code == 200, sa_resp.text
    assert sa_resp.headers["content-type"] == human_resp.headers["content-type"]
    assert sa_resp.content == human_resp.content


async def test_export_route_out_of_scope_is_denied(client, seeded, processing_env) -> None:  # noqa: ANN001
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    service_account = await _create_service_account(
        client,
        admin_headers,
        organization_id=seeded["org_a"],
        scopes=["conversation:read"],  # no document:read
        owner_user_id=seeded["alice_id"],
    )

    user_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, user_headers, seeded["org_a"], processing_env
    )

    resp = await client.get(
        f"/api/v1/integrations/api/conversations/{conversation_id}/document/export?format=text",
        headers={"Authorization": f"Bearer {service_account['api_key']}"},
    )
    assert resp.status_code == 403


async def test_create_participant_without_owner_succeeds(client, seeded) -> None:
    """No `_require_owner()` guard on this route -- unlike the write
    routes for conversations/documents, a participant is never
    attributed to a user, so a service account scoped only for this
    (e.g. the GDT connector prototype, which needs no human owner to add
    a PATIENT participant from an inbound file) must succeed with
    `owner_user_id=None`."""
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    sa_resp = await client.post(
        "/api/v1/admin/service-accounts",
        json={
            "name": "gdt-bridge-no-owner",
            "organization_id": seeded["org_a"],
            "scopes": ["conversation:manage-participants"],
            "owner_user_id": None,
        },
        headers=admin_headers,
    )
    assert sa_resp.status_code == 201, sa_resp.text
    api_key = sa_resp.json()["api_key"]

    user_headers = await login(client, "alice", "a very strong password 123")
    create_resp = await client.post(
        "/api/v1/conversations",
        json={"title": "GDT-created conversation", "organization_id": seeded["org_a"]},
        headers=user_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    conversation_id = create_resp.json()["id"]

    participant_resp = await client.post(
        f"/api/v1/integrations/api/conversations/{conversation_id}/participants",
        json={"display_name": "Herr M.", "participant_type": "patient"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert participant_resp.status_code == 201, participant_resp.text
    assert participant_resp.json()["display_name"] == "Herr M."
