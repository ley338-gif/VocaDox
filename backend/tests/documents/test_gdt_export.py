"""GDT export (ADR-0041): both variants (PDF-reference bundle, embedded
text) produce real, decodable GDT records, and -- mirroring the
existing FHIR export's discipline -- never fabricate patient fields
VocaDox wasn't actually given."""

from __future__ import annotations

import io
import uuid
import zipfile

from app.documents.gdt_line_codec import GdtCharset, decode_lines, python_codec_name

from tests.conversations.conftest import login
from tests.documents._seed import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)

_CODEC = python_codec_name(GdtCharset.ISO8859_1)


async def test_export_gdt_text(client, seeded, processing_env) -> None:  # noqa: ANN001
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
        f"/api/v1/conversations/{conversation_id}/document/export?format=gdt-text",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in resp.headers["content-disposition"]

    fields = decode_lines(resp.content.decode(_CODEC))
    field_dict = dict(fields)
    assert field_dict["8000"] == "6310"
    assert field_dict["3000"] == "PVS-4711"
    assert field_dict["3101"] == "Herr M."
    assert "3102" not in field_dict  # never split into a fabricated first name
    assert "3103" not in field_dict  # no DOB anywhere in VocaDox -- always omitted
    comment_text = "".join(content for fk, content in fields if fk == "6227")
    assert "Ramipril" in comment_text


async def test_export_gdt_pdf(client, seeded, processing_env) -> None:  # noqa: ANN001
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
        f"/api/v1/conversations/{conversation_id}/document/export?format=gdt-pdf", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/zip")
    assert "attachment" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = archive.namelist()
        pdf_names = [n for n in names if n.endswith(".pdf")]
        gdt_names = [n for n in names if n.endswith(".gdt")]
        assert len(pdf_names) == 1
        assert len(gdt_names) == 1
        assert archive.read(pdf_names[0])[:4] == b"%PDF"

        fields = decode_lines(archive.read(gdt_names[0]).decode(_CODEC))
        field_dict = dict(fields)
        assert field_dict["6302"] == "1"
        assert field_dict["6303"] == "PDF"
        assert field_dict["6304"]
        # The .gdt file must reference the exact PDF filename bundled
        # alongside it -- a connector rewrites this to a real path later
        # (see ADR-0041), but within the zip the two must agree.
        assert field_dict["6305"] == pdf_names[0]


async def test_export_gdt_without_patient_participant_omits_patient_fields(
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
        f"/api/v1/conversations/{conversation_id}/document/export?format=gdt-text",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    field_dict = dict(decode_lines(resp.content.decode(_CODEC)))
    for feldkennung in ("3000", "3101", "3102", "3103"):
        assert feldkennung not in field_dict, f"field {feldkennung} must never be fabricated"
