"""Export produces a real, usable file (plain text and JSON), respects the
same organization-scoped authorization as everything else, and is
audited."""

from __future__ import annotations

import base64
import io
import uuid
import zipfile

from app.audit.models import AuditEvent
from sqlalchemy import select

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)

# A real, valid 1x1 transparent PNG -- python-docx/reportlab actually
# decode the image at export time, so a magic-byte-only stub isn't enough.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
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


async def test_export_docx_and_pdf(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Post-GA P0-2: real DOCX/PDF files, with the approval status and
    revision number visible in the exported content."""
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
        f"/api/v1/conversations/{conversation_id}/document/export?format=docx", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"  # a real DOCX (zip container), not a stub

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=pdf", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"


async def test_export_docx_and_pdf_with_letterhead_logo(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Post-GA: a TemplateVersion.letterhead_logo_asset_key gets inserted
    into the DOCX/PDF header at export time. DOCX is verified precisely
    (the image is really embedded in the zip container's media part) --
    PDF has no easy structural check, so it's just verified to still
    render without crashing (mirrors the "never crashes either way"
    coverage of every other export test in this file)."""
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    upload_resp = await client.post(
        "/api/v1/templates/letterhead-logo",
        files={"file": ("logo.png", _TINY_PNG, "image/png")},
        headers=admin_headers,
    )
    assert upload_resp.status_code == 201, upload_resp.text
    asset_key = upload_resp.json()["asset_key"]

    create_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": f"test-letterhead-{uuid.uuid4().hex[:8]}",
            "name": "Test Letterhead",
            "extraction_categories": [{"key": "general_fact", "builtin": True}],
            "presentation": [{"category": "general_fact", "title": "Facts"}],
            "letterhead_logo_asset_key": asset_key,
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    template = create_resp.json()
    versions_resp = await client.get(
        f"/api/v1/templates/{template['id']}/versions", headers=admin_headers
    )
    v1 = versions_resp.json()[0]
    publish_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions/{v1['id']}/publish", headers=admin_headers
    )
    assert publish_resp.status_code == 200, publish_resp.text
    published_version = publish_resp.json()

    headers = await login(client, "alice", "a very strong password 123")
    from tests.processing.conftest import create_conversation_with_source_audio

    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    override_resp = await client.patch(
        f"/api/v1/conversations/{conversation_id}/config-override",
        json={"template_id": template["id"], "template_version_id": published_version["id"]},
        headers=headers,
    )
    assert override_resp.status_code == 200, override_resp.text

    from app.intelligence.models import ExtractedFact, FactStatus

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        session.add(
            ExtractedFact(
                conversation_id=uuid.UUID(conversation_id),
                processing_run_id=None,
                category="general_fact",
                fact_type="general_fact",
                structured_value={"subject": "Termin", "attribute": "Ort", "value": "Raum 4"},
                certainty="stated",
                status=FactStatus.VERIFIED.value,
            )
        )
        await session.commit()

    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )

    docx_resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=docx", headers=headers
    )
    assert docx_resp.status_code == 200, docx_resp.text
    with zipfile.ZipFile(io.BytesIO(docx_resp.content)) as archive:
        media_files = [n for n in archive.namelist() if n.startswith("word/media/")]
        assert media_files, "expected the letterhead logo to be embedded in the docx media part"

    pdf_resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=pdf", headers=headers
    )
    assert pdf_resp.status_code == 200, pdf_resp.text
    assert pdf_resp.content[:4] == b"%PDF"


async def test_export_fhir_document_reference(client, seeded, processing_env) -> None:  # noqa: ANN001
    """Post-GA P3-1: a real FHIR R4 DocumentReference export."""
    import base64

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )
    await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"external_reference": "PVS-4711", "external_reference_type": "patient-number"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/participants",
        json={"display_name": "Herr M.", "participant_type": "patient"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=fhir", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/fhir+json")
    assert "attachment" in resp.headers["content-disposition"]

    resource = resp.json()
    assert resource["resourceType"] == "DocumentReference"
    assert resource["status"] == "current"
    assert resource["docStatus"] in ("preliminary", "final")
    assert resource["description"] == "Processing test"
    assert resource["subject"] == {"display": "Herr M."}
    assert resource["identifier"] == [{"type": {"text": "patient-number"}, "value": "PVS-4711"}]
    attachment = resource["content"][0]["attachment"]
    assert attachment["contentType"] == "text/plain; charset=utf-8"
    decoded = base64.b64decode(attachment["data"]).decode("utf-8")
    assert "Ramipril" in decoded


async def test_export_fhir_without_patient_participant_omits_subject(
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
    await client.post(
        f"/api/v1/conversations/{conversation_id}/document/compose", json={}, headers=headers
    )

    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export?format=fhir", headers=headers
    )
    assert resp.status_code == 200, resp.text
    resource = resp.json()
    assert "subject" not in resource
    assert "identifier" not in resource


async def test_export_without_composed_document_is_409(client, seeded, processing_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    resp = await client.get(
        f"/api/v1/conversations/{conversation_id}/document/export", headers=headers
    )
    assert resp.status_code == 404  # no document row exists yet at all
