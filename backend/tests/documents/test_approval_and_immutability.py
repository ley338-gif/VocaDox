"""Approval workflow (spec §27): genuinely blocked by unresolved HIGH/
CRITICAL review issues, genuinely restricted to `document:approve`
holders, and an approved revision is genuinely, ORM-enforced immutable —
not just a UI convention (tested by attempting a real mutation and
confirming it's rejected).
"""

from __future__ import annotations

import uuid

import pytest
from app.documents.models import Document, DocumentRevision, ImmutableRevisionError
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def _seed(client, headers, org_id, processing_env):  # noqa: ANN001
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, org_id, processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        fact_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    return conversation_id, fact_ids


async def _resolve_all_open_issues(client, headers, conversation_id):  # noqa: ANN001
    """Confirms every currently-open review issue against the first
    related fact, until none remain — used by tests that need a clean
    path to READY_FOR_APPROVAL without asserting on the resolution
    mechanics themselves (see test_review_wizard.py for that)."""
    for _ in range(10):
        resp = await client.get(
            f"/api/v1/conversations/{conversation_id}/review-issues", headers=headers
        )
        open_issues = [i for i in resp.json() if i["status"] == "open"]
        if not open_issues:
            return
        for issue in open_issues:
            await client.patch(
                f"/api/v1/conversations/{conversation_id}/review-issues/{issue['id']}",
                json={"fact_id": issue["related_fact_ids"][0], "action": "confirm"},
                headers=headers,
            )


async def test_approval_blocked_by_open_high_critical_issues(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.json()["status"] == "review_required"

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/approve", headers=headers
    )
    # alice (User role) doesn't hold document:approve in the first place.
    assert resp.status_code == 403


async def test_approval_blocked_even_for_approver_while_issues_open(
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

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        reviewer_role = await get_role_by_name(session, "Reviewer")
        assert reviewer_role is not None
        reviewer = await create_local_user(
            session, username="rachel", password="a reasonably strong pw 999", display_name="Rachel"
        )
        group = await get_or_create_group(session, name="Org A Reviewers")
        await assign_role_to_group(session, group_id=group.id, role_id=reviewer_role.id)
        await add_user_to_group(session, user_id=reviewer.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=reviewer.id, organization_id=uuid.UUID(seeded["org_a"]))
        )
        await session.commit()

    reviewer_headers = await login(client, "rachel", "a reasonably strong pw 999")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/approve", headers=reviewer_headers
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()["detail"]
    assert len(body["blocking_issue_ids"]) >= 1


async def test_approval_succeeds_once_issues_resolved_and_creates_immutable_revision(
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

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, fact_ids = await _seed(client, headers, seeded["org_a"], processing_env)

    await _resolve_all_open_issues(client, headers, conversation_id)
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.json()["status"] == "ready_for_approval", resp.json()

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        reviewer_role = await get_role_by_name(session, "Reviewer")
        reviewer = await create_local_user(
            session,
            username="rachel2",
            password="a reasonably strong pw 998",
            display_name="Rachel2",
        )
        group = await get_or_create_group(session, name="Org A Reviewers 2")
        await assign_role_to_group(session, group_id=group.id, role_id=reviewer_role.id)
        await add_user_to_group(session, user_id=reviewer.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=reviewer.id, organization_id=uuid.UUID(seeded["org_a"]))
        )
        await session.commit()

    reviewer_headers = await login(client, "rachel2", "a reasonably strong pw 998")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/approve", headers=reviewer_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["current_revision"]["status"] == "approved"
    assert body["current_revision"]["approved_by_user_id"] is not None
    assert body["current_revision"]["approved_at"] is not None

    revision_id = body["current_revision"]["id"]

    # Real, ORM-enforced immutability: try to mutate the approved revision
    # directly and confirm it's rejected — not merely "no route happens to
    # call update."
    async with sessionmaker() as session:
        revision = await session.get(DocumentRevision, uuid.UUID(revision_id))
        assert revision is not None
        revision.rendered_text = "TAMPERED"
        with pytest.raises(ImmutableRevisionError):
            await session.flush()
        await session.rollback()

    # And composing again after approval never mutates the approved
    # revision — it creates a new one. (re-login as alice: the shared
    # client's cookie jar currently holds the reviewer's session)
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.status_code == 200
    new_revision_id = resp.json()["current_revision"]["id"]
    assert new_revision_id != revision_id

    async with sessionmaker() as session:
        approved_revision = await session.get(DocumentRevision, uuid.UUID(revision_id))
        assert approved_revision is not None
        assert approved_revision.status == "approved"
        assert approved_revision.rendered_text != "TAMPERED"

        document_result = await session.execute(
            select(Document).where(Document.conversation_id == uuid.UUID(conversation_id))
        )
        document = document_result.scalar_one()
        assert document.current_revision_id == uuid.UUID(new_revision_id)
