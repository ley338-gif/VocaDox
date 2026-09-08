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
from tests.processing.conftest import create_conversation_with_source_audio


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


async def test_recompose_after_reextraction_excludes_superseded_facts(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """A fact superseded by a later extraction run must never appear in a
    freshly composed document -- otherwise re-processing a conversation
    would duplicate every line in the Dokumentation."""
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    import uuid as _uuid

    async with sessionmaker() as session:
        first_run_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=_uuid.UUID(conversation_id)
        )
    async with sessionmaker() as session:
        second_run_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=_uuid.UUID(conversation_id)
        )

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    revision = resp.json()["current_revision"]

    all_fact_ids_in_content = {
        fid
        for section in revision["structured_content"]
        for statement in section["statements"]
        for fid in statement["fact_ids"]
    }
    assert all_fact_ids_in_content == {str(v) for v in second_run_ids.values()}
    assert not (all_fact_ids_in_content & {str(v) for v in first_run_ids.values()})


async def test_medical_consultation_template_composes_as_letter(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """post-GA: a conversation whose effective template is
    "medical_consultation" (document_layout="letter") composes its
    Document into a formal-letter shape -- German section titles from the
    template's own `presentation`, and `document_layout="letter"` on the
    revision -- instead of the default flat-section layout every other
    template uses. Proves the layout choice is real, template-driven
    behavior (via the same conversation-override mechanism
    test_meeting_vs_general_e2e.py already proves for extraction
    categories), not a hardcoded flag."""
    headers = await login(client, "alice", "a very strong password 123")
    _, sessionmaker, _queue, _storage = processing_env

    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )

    templates_resp = await client.get("/api/v1/templates", headers=headers)
    by_key = {t["key"]: t for t in templates_resp.json()}
    medical_template = by_key["medical_consultation"]
    versions_resp = await client.get(
        f"/api/v1/templates/{medical_template['id']}/versions", headers=headers
    )
    medical_version = next(v for v in versions_resp.json() if v["status"] == "published")
    assert medical_version["document_layout"] == "letter"

    override_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/config-override",
        json={
            "template_id": medical_template["id"],
            "template_version_id": medical_version["id"],
        },
        headers=headers,
    )
    assert override_resp.status_code == 200, override_resp.text

    import uuid as _uuid

    from app.intelligence.models import ExtractedFact, FactStatus

    async with sessionmaker() as session:
        session.add_all(
            [
                ExtractedFact(
                    conversation_id=_uuid.UUID(conversation_id),
                    processing_run_id=None,
                    category="diagnosis",
                    fact_type="diagnosis",
                    structured_value={"description": "Akute Bronchitis"},
                    certainty="stated",
                    status=FactStatus.VERIFIED.value,
                ),
                ExtractedFact(
                    conversation_id=_uuid.UUID(conversation_id),
                    processing_run_id=None,
                    category="symptom",
                    fact_type="symptom",
                    structured_value={
                        "description": "Husten seit 3 Tagen",
                        "onset": "vor 3 Tagen",
                        "severity": "mittel",
                    },
                    certainty="stated",
                    status=FactStatus.VERIFIED.value,
                ),
            ]
        )
        await session.commit()

    compose_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )
    assert compose_resp.status_code == 200, compose_resp.text
    revision = compose_resp.json()["current_revision"]
    assert revision["document_layout"] == "letter"
    titles = {s["title"] for s in revision["structured_content"]}
    assert "Diagnose" in titles
    assert "Anamnese" in titles
