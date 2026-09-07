"""Cross-conversation search (post-GA P0-1): finds content from all three
indexed source types, respects the same org/team scoping as
`GET /conversations`, and never accumulates duplicate entries across
re-extraction/re-composition. Runs against SQLite (see
`app.search.service`'s dialect fallback / ADR-0030), so this proves
scoping/upsert/permission behavior, not real German full-text ranking.
"""

from __future__ import annotations

import uuid

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def test_search_finds_transcript_segment_content(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    segment_text = resp.json()[0]["original_text"]
    needle = segment_text.split()[0]

    resp = await client.get(f"/api/v1/search?q={needle}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    hit = next(h for h in body["items"] if h["source_type"] == "transcript_segment")
    assert hit["conversation_id"] == conversation_id
    assert needle.lower() in hit["snippet"].lower()


async def test_search_finds_corrected_segment_text_not_the_original(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    segment_id = resp.json()[0]["id"]

    resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/transcript/segments/{segment_id}",
        json={"corrected_text": "Ein völlig einzigartiger Korrekturtext Zebraflunder."},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/search?q=Zebraflunder", headers=headers)
    hits = [h for h in resp.json()["items"] if h["source_type"] == "transcript_segment"]
    assert len(hits) == 1
    assert hits[0]["conversation_id"] == conversation_id


async def test_search_deleted_conversation_is_removed_from_index(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=headers
    )
    needle = resp.json()[0]["original_text"].split()[0]

    resp = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert resp.status_code == 204, resp.text

    resp = await client.get(f"/api/v1/search?q={needle}", headers=headers)
    assert resp.json()["items"] == []


async def test_search_finds_fact_and_document_content(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )

    resp = await client.get("/api/v1/search?q=Ramipril", headers=headers)
    assert resp.status_code == 200, resp.text
    fact_hits = [h for h in resp.json()["items"] if h["source_type"] == "extracted_fact"]
    assert fact_hits, "expected at least one extracted_fact hit for 'Ramipril'"
    assert all(h["conversation_id"] == conversation_id for h in fact_hits)

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/search?q=Ramipril", headers=headers)
    doc_hits = [h for h in resp.json()["items"] if h["source_type"] == "document"]
    assert len(doc_hits) == 1
    assert doc_hits[0]["conversation_id"] == conversation_id


async def test_search_recompose_does_not_duplicate_document_hits(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )

    for _ in range(2):
        resp = await client.post(
            f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
        )
        assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/search?q=Ramipril", headers=headers)
    doc_hits = [h for h in resp.json()["items"] if h["source_type"] == "document"]
    assert len(doc_hits) == 1  # never one stale entry per past revision


async def test_search_reextraction_does_not_leave_stale_fact_hits(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """A re-extraction supersedes the previous run's facts (#61) -- their
    search entries must disappear too, not linger as stale duplicates
    alongside the new ones."""
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    conversation_uuid = uuid.UUID(conversation_id)
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=conversation_uuid
        )
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=conversation_uuid
        )

    resp = await client.get("/api/v1/search?q=Ramipril", headers=headers)
    fact_hits = [h for h in resp.json()["items"] if h["source_type"] == "extracted_fact"]
    assert len(fact_hits) == 2  # the "5mg" + "10mg" dose facts, once each -- not four


async def test_search_is_organization_scoped(client, seeded, processing_env) -> None:  # noqa: ANN001
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/transcript/segments", headers=alice_headers
    )
    needle = resp.json()[0]["original_text"].split()[0]

    bob_headers = await login(client, "bob", "another very strong pw 456")
    resp = await client.get(f"/api/v1/search?q={needle}", headers=bob_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_search_requires_permission(client, seeded, processing_env) -> None:  # noqa: ANN001
    from app.identity.service import add_user_to_group, create_local_user, get_or_create_group

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        user = await create_local_user(
            session, username="no_perms", password="a reasonably strong pw 999", display_name="X"
        )
        group = await get_or_create_group(session, name="No Perms Group")
        # Deliberately no role assigned -> no permissions at all.
        await add_user_to_group(session, user_id=user.id, group_id=group.id)
        await session.commit()

    headers = await login(client, "no_perms", "a reasonably strong pw 999")
    resp = await client.get("/api/v1/search?q=anything", headers=headers)
    assert resp.status_code == 403
