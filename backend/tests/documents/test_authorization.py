"""Organization-scoped authorization for every new Phase 5 endpoint,
tested as heavily as every prior phase: cross-org UUID guessing must
return 404, never 403 (never confirms the resource exists)."""

from __future__ import annotations

import uuid

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def test_cross_organization_document_endpoints_return_404(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        fact_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=alice_headers
    )

    bob_headers = await login(client, "bob", "another very strong pw 456")

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/revisions", headers=bob_headers
    )
    assert resp.status_code == 404

    # bob (User role) doesn't hold document:approve at all, so that
    # endpoint 403s on the permission check before ever reaching the
    # organization check — see test_missing_permission_is_rejected's
    # Phase 4 precedent for why permission is checked first. Approve's own
    # cross-org 404 is proven below with a user who legitimately holds
    # document:approve in a different organization.
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/review-issues", headers=bob_headers
    )
    assert resp.status_code == 404

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/review-issues/{uuid.uuid4()}",
        json={"fact_id": str(fact_ids["clean_fact_id"]), "action": "confirm"},
        headers=bob_headers,
    )
    assert resp.status_code == 404


async def test_cross_organization_approve_returns_404_for_a_user_who_holds_the_permission(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Proves the approve endpoint's own org check independent of the
    permission check above: a Reviewer (holds document:approve) in Org B
    must still get 404, never confirmation the Org A conversation exists."""
    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
        reviewer_role = await get_role_by_name(session, "Reviewer")
        assert reviewer_role is not None
        outsider = await create_local_user(
            session,
            username="oscar",
            password="a reasonably strong pw 777",
            display_name="Oscar",
        )
        group = await get_or_create_group(session, name="Org B Reviewers")
        await assign_role_to_group(session, group_id=group.id, role_id=reviewer_role.id)
        await add_user_to_group(session, user_id=outsider.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=outsider.id, organization_id=uuid.UUID(seeded["org_b"]))
        )
        await session.commit()

    alice_headers = await login(client, "alice", "a very strong password 123")
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=alice_headers
    )

    outsider_headers = await login(client, "oscar", "a reasonably strong pw 777")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/approve", headers=outsider_headers
    )
    assert resp.status_code == 404


async def test_document_edit_permission_required_to_compose(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        auditor_role = await get_role_by_name(session, "Auditor")
        assert auditor_role is not None
        dana = await create_local_user(
            session, username="dana2", password="a reasonably strong pw 001", display_name="Dana2"
        )
        group = await get_or_create_group(session, name="Org A Auditors 2")
        await assign_role_to_group(session, group_id=group.id, role_id=auditor_role.id)
        await add_user_to_group(session, user_id=dana.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=dana.id, organization_id=uuid.UUID(seeded["org_a"]))
        )
        await session.commit()

    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )

    # (the shared httpx client keeps one cookie jar, so each login() call
    # replaces the active session — every action for a given user must
    # happen right after that user's own login(), never interleaved)
    dana_headers = await login(client, "dana2", "a reasonably strong pw 001")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=dana_headers
    )
    assert resp.status_code == 403  # Auditor has document:read but not document:edit

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document", headers=dana_headers
    )
    assert resp.status_code == 404  # no document composed yet, but permission itself is fine

    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=alice_headers
    )
    assert resp.status_code == 200, resp.text

    dana_headers = await login(client, "dana2", "a reasonably strong pw 001")
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document", headers=dana_headers
    )
    assert resp.status_code == 200  # Auditor does have document:read
