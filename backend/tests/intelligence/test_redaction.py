"""Post-GA P3-2: fact-level redaction — hides content from every shared/
rendered output (Document composition here; search/Ask VocaDox share the
same render_fact_statement so are covered by construction) while
preserving the fact row, its evidence, and an audit trail.
"""

from __future__ import annotations

import uuid

from app.audit.models import AuditEvent
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def _find_fact_id(client, headers, conversation_id, needle: str) -> str:  # noqa: ANN001
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    assert resp.status_code == 200
    for fact in resp.json():
        value = fact["structured_value"]
        if needle in str(value):
            return fact["id"]
    raise AssertionError(f"no fact containing {needle!r}")


async def test_redact_fact_hides_content_from_document_composition(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    fact_id = await _find_fact_id(client, headers, conversation_id, "Follow-up clinic")

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/redact",
        json={"reason": "sensitive location"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_redacted"] is True
    # Real content is still returned by the internal, authorized Facts view.
    assert "Follow-up clinic" in str(resp.json()["structured_value"])

    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    export = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=text", headers=headers
    )
    assert export.status_code == 200
    assert "Follow-up clinic" not in export.text
    assert "[Geschwärzt]" in export.text


async def test_unredact_restores_content_in_composition(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    fact_id = await _find_fact_id(client, headers, conversation_id, "Follow-up clinic")

    await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/redact",
        json={},
        headers=headers,
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/unredact",
        json={"reason": "no longer sensitive"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_redacted"] is False

    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    export = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=text", headers=headers
    )
    assert "Follow-up clinic" in export.text


async def test_redact_and_unredact_are_audited(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    fact_id = await _find_fact_id(client, headers, conversation_id, "Follow-up clinic")

    await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/redact",
        json={"reason": "sensitive"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/unredact",
        json={},
        headers=headers,
    )

    async with sessionmaker() as session:
        result = await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type.in_(["fact.redacted", "fact.unredacted"])
            )
        )
        events = result.scalars().all()
        assert {e.event_type for e in events} == {"fact.redacted", "fact.unredacted"}
        for event in events:
            # Never fact content in audit metadata (spec §63).
            assert "Follow-up clinic" not in str(event.event_metadata)


async def test_redact_requires_permission(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Auditor has fact:read but not fact:redact."""
    import uuid as _uuid

    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

    headers = await login(client, "carol", "yet another strong pw 789")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    fact_id = await _find_fact_id(client, headers, conversation_id, "Follow-up clinic")

    async with sessionmaker() as session:
        auditor_role = await get_role_by_name(session, "Auditor")
        assert auditor_role is not None
        dana = await create_local_user(
            session, username="dana", password="a reasonably strong pw 000", display_name="Dana"
        )
        group = await get_or_create_group(session, name="Org A Auditors")
        await assign_role_to_group(session, group_id=group.id, role_id=auditor_role.id)
        await add_user_to_group(session, user_id=dana.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=dana.id, organization_id=_uuid.UUID(seeded["org_a"]))
        )
        await session.commit()

    dana_headers = await login(client, "dana", "a reasonably strong pw 000")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/facts/{fact_id}/redact",
        json={},
        headers=dana_headers,
    )
    assert resp.status_code == 403
