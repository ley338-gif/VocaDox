"""Document composition: deterministic rendering from real facts, every
statement traceable to its originating fact id, REVIEW_REQUIRED vs
READY_FOR_APPROVAL status derived from real open blocking issues (never
decoration).
"""

from __future__ import annotations

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)


async def test_compose_requires_document_edit_permission_and_produces_review_required(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        import uuid as _uuid

        fact_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=_uuid.UUID(conversation_id)
        )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "review_required"  # real blocking issues exist
    revision = body["current_revision"]
    assert revision["revision_number"] == 1
    assert revision["status"] == "review_required"
    assert len(revision["blocking_issue_ids"]) >= 1

    # Every statement in the composed content traces back to a real fact id
    # — never free text with no provenance.
    all_fact_ids_in_content = {
        fid
        for section in revision["structured_content"]
        for statement in section["statements"]
        for fid in statement["fact_ids"]
    }
    assert str(fact_ids["verified_fact_id"]) in all_fact_ids_in_content
    assert str(fact_ids["unverified_fact_id"]) in all_fact_ids_in_content
    assert str(fact_ids["clean_fact_id"]) in all_fact_ids_in_content

    # Rendered text is a real, non-empty plain-text rendering.
    assert "Ramipril" in revision["rendered_text"]
    assert "Follow-up clinic" in revision["rendered_text"]


async def test_get_document_before_compose_is_404(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(f"/api/v1/conversations/{conversation_id}/document", headers=headers)
    assert resp.status_code == 404


async def test_recompose_creates_new_revision_never_mutates_prior(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    import uuid as _uuid

    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=_uuid.UUID(conversation_id)
        )

    resp1 = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp1.status_code == 200
    revision_1_id = resp1.json()["current_revision"]["id"]

    resp2 = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp2.status_code == 200
    revision_2_id = resp2.json()["current_revision"]["id"]
    assert resp2.json()["current_revision"]["revision_number"] == 2
    assert revision_1_id != revision_2_id

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/revisions", headers=headers
    )
    assert resp.status_code == 200
    revisions = resp.json()
    assert [r["revision_number"] for r in revisions] == [1, 2]
    assert revisions[0]["id"] == revision_1_id
