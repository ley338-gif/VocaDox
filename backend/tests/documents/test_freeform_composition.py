"""Freeform document_layout (post-GA): placeholder substitution from real
facts in category order, an honest fallback for a placeholder with no
matching fact (never fabricated content), and the resulting
DocumentRevision's fact_ids only ever reflecting evidence actually used
in the rendered text — never padded, never dropped.
"""

from __future__ import annotations

import uuid as _uuid

from app.intelligence.models import ExtractedFact, FactStatus

from tests.conversations.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio


async def _create_published_freeform_template(client, headers, *, document_body: str) -> dict:  # noqa: ANN001
    create_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": f"test-freeform-{_uuid.uuid4().hex[:8]}",
            "name": "Test Freeform",
            "extraction_categories": [
                {"key": "general_fact", "builtin": True},
                {"key": "decision", "builtin": True},
            ],
            "presentation": [
                {"category": "general_fact", "title": "Facts"},
                {"category": "decision", "title": "Decisions"},
            ],
            "document_layout": "freeform",
            "document_body": document_body,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    template = create_resp.json()
    versions_resp = await client.get(
        f"/api/v1/templates/{template['id']}/versions", headers=headers
    )
    v1 = versions_resp.json()[0]
    publish_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions/{v1['id']}/publish", headers=headers
    )
    assert publish_resp.status_code == 200, publish_resp.text
    return {"template": template, "version": publish_resp.json()}


async def _override_and_compose(client, headers, conversation_id, created):  # noqa: ANN001
    override_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/config-override",
        json={
            "template_id": created["template"]["id"],
            "template_version_id": created["version"]["id"],
        },
        headers=headers,
    )
    assert override_resp.status_code == 200, override_resp.text
    compose_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert compose_resp.status_code == 200, compose_resp.text
    return compose_resp.json()["current_revision"]


async def test_freeform_placeholders_substitute_real_facts_in_order(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_published_freeform_template(
        client,
        admin_headers,
        document_body=(
            "Sehr geehrte Kolleginnen und Kollegen,\n\n"
            "wir berichten über folgende Entscheidungen: [decision_1] sowie [decision_2].\n\n"
            "Mit freundlichen Grüßen"
        ),
    )

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        session.add_all(
            [
                ExtractedFact(
                    conversation_id=_uuid.UUID(conversation_id),
                    processing_run_id=None,
                    category="decision",
                    fact_type="decision",
                    structured_value={"description": "Antibiotikum ansetzen"},
                    certainty="stated",
                    status=FactStatus.VERIFIED.value,
                ),
                ExtractedFact(
                    conversation_id=_uuid.UUID(conversation_id),
                    processing_run_id=None,
                    category="decision",
                    fact_type="decision",
                    structured_value={"description": "Wiedervorstellung in 2 Wochen"},
                    certainty="stated",
                    status=FactStatus.VERIFIED.value,
                ),
            ]
        )
        await session.commit()

    revision = await _override_and_compose(client, headers, conversation_id, created)
    assert revision["document_layout"] == "freeform"
    assert len(revision["structured_content"]) == 1
    section = revision["structured_content"][0]
    assert section["title"] is None
    assert len(section["statements"]) == 1
    text = section["statements"][0]["text"]
    assert "Antibiotikum ansetzen" in text
    assert "Wiedervorstellung in 2 Wochen" in text
    assert "[decision_1]" not in text
    assert "[decision_2]" not in text

    # fact_ids reflects exactly the facts actually substituted -- no more,
    # no less (the evidence-chain invariant every other layout also upholds).
    facts_resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    all_fact_ids = {f["id"] for f in facts_resp.json()}
    assert set(section["statements"][0]["fact_ids"]) == all_fact_ids


async def test_freeform_missing_placeholder_renders_honest_fallback_not_fabricated(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_published_freeform_template(
        client,
        admin_headers,
        document_body="Entscheidung: [decision_1]. Zweite Entscheidung: [decision_2].",
    )

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        session.add(
            ExtractedFact(
                conversation_id=_uuid.UUID(conversation_id),
                processing_run_id=None,
                category="decision",
                fact_type="decision",
                structured_value={"description": "Antibiotikum ansetzen"},
                certainty="stated",
                status=FactStatus.VERIFIED.value,
            )
        )
        await session.commit()

    revision = await _override_and_compose(client, headers, conversation_id, created)
    text = revision["structured_content"][0]["statements"][0]["text"]
    assert "Antibiotikum ansetzen" in text
    # Only one real decision exists -- [decision_2] must render an honest,
    # non-fabricated fallback, never invented content.
    assert "[nicht erfasst: decision_2]" in text

    facts_resp = await client.get(f"/api/v1/conversations/{conversation_id}/facts", headers=headers)
    only_fact_id = facts_resp.json()[0]["id"]
    assert revision["structured_content"][0]["statements"][0]["fact_ids"] == [only_fact_id]


async def test_freeform_with_no_facts_at_all_still_composes(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    created = await _create_published_freeform_template(
        client, admin_headers, document_body="Kein Fakt hier: [decision_1]."
    )

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    revision = await _override_and_compose(client, headers, conversation_id, created)
    text = revision["structured_content"][0]["statements"][0]["text"]
    assert "[nicht erfasst: decision_1]" in text
    assert revision["structured_content"][0]["statements"][0]["fact_ids"] == []
