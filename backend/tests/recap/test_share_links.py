"""Post-GA P3-2: expiring, unauthenticated share links for an approved
Recap. Reuses test_recap.py's own conversation/document seeding helpers.
Uses only the admin user throughout (system:admin bypasses every
permission check) -- avoids the shared single-client-cookie-jar pitfall
of logging in as a second user mid-test.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from app.recap.models import RecapShareLink
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.recap.test_recap import _create_conversation, _seed_document


async def _generate_and_approve_recap(client, headers, conversation_id) -> None:  # noqa: ANN001
    await client.post(f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers)
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/approve", headers=headers
    )
    assert resp.status_code == 200, resp.text


async def test_create_share_link_requires_approved_recap(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await client.post(f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers)

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/share-links",
        json={"ttl_hours": 24},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


async def test_create_share_link_and_public_access(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await _generate_and_approve_recap(client, headers, conversation_id)

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/share-links",
        json={"ttl_hours": 24},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    link = resp.json()
    assert link["access_count"] == 0

    # No auth headers at all -- this is the public, unauthenticated path.
    public_resp = await client.get(f"/api/v1/public/recap/{link['token']}")
    assert public_resp.status_code == 200, public_resp.text
    assert public_resp.headers["cache-control"] == "no-store, private"
    assert public_resp.headers["referrer-policy"] == "no-referrer"
    body = public_resp.json()
    assert body["content"]
    assert body["revision_number"] == 1

    # Access is tracked.
    list_resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap/share-links", headers=headers
    )
    assert list_resp.json()[0]["access_count"] == 1
    assert "token" not in list_resp.json()[0]

    # The raw bearer token is one-time output and is not recoverable from
    # the database row after creation.
    async with sessionmaker() as session:
        stored_result = await session.execute(
            select(RecapShareLink).where(
                RecapShareLink.token_hash == hashlib.sha256(link["token"].encode()).hexdigest()
            )
        )
        stored = stored_result.scalar_one_or_none()
        assert stored is not None
        assert stored.token_hash == hashlib.sha256(link["token"].encode()).hexdigest()
        assert stored.token_hash != link["token"]


async def test_public_access_nonexistent_token_is_404(client) -> None:  # noqa: ANN001
    resp = await client.get("/api/v1/public/recap/not-a-real-token")
    assert resp.status_code == 404


async def test_public_access_expired_token_is_404(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await _generate_and_approve_recap(client, headers, conversation_id)

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/share-links",
        json={"ttl_hours": 1},
        headers=headers,
    )
    token = resp.json()["token"]

    async with sessionmaker() as session:
        result = await session.execute(
            select(RecapShareLink).where(
                RecapShareLink.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
        link = result.scalar_one()
        link.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    public_resp = await client.get(f"/api/v1/public/recap/{token}")
    assert public_resp.status_code == 404


async def test_revoke_share_link_blocks_public_access(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await _generate_and_approve_recap(client, headers, conversation_id)

    create_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/share-links",
        json={"ttl_hours": 24},
        headers=headers,
    )
    link = create_resp.json()

    revoke_resp = await client.delete(
        f"/api/v1/conversations/{conversation_id}/recap/share-links/{link['id']}",
        headers=headers,
    )
    assert revoke_resp.status_code == 204

    public_resp = await client.get(f"/api/v1/public/recap/{link['token']}")
    assert public_resp.status_code == 404
