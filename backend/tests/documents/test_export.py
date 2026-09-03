"""Export produces a real, usable file (plain text and JSON), respects the
same organization-scoped authorization as everything else, and is
audited."""

from __future__ import annotations

import uuid

from app.audit.models import AuditEvent
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def test_export_text_and_json(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=text", headers=headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "Ramipril" in resp.text

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=json", headers=headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    payload = resp.json()
    assert payload["conversation_id"] == conversation_id
    assert payload["sections"]

    async with sessionmaker() as session:
        result = await session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "document.exported")
        )
        events = result.scalars().all()
        assert len(events) == 2
        for event in events:
            # Never full document content in audit metadata (spec §63).
            assert "Ramipril" not in str(event.event_metadata)


async def test_export_without_composed_document_is_409(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export", headers=headers
    )
    assert resp.status_code == 404  # no document row exists yet at all
