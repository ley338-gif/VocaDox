"""Recap generation/approval: requires a composed Document first, uses the
FakeLLMProvider in tests (default when VOCADOX_LLM_PROVIDER isn't set to
"ollama" — same convention every other LLM-touching test in this project
relies on), approval is human-only and genuinely immutable afterward, and
cross-organization access is denied like every other conversation-scoped
resource.
"""

from __future__ import annotations

import uuid

import pytest
from app.documents.models import Document, DocumentRevision, DocumentRevisionStatus
from app.media.models import MediaAsset
from app.recap.models import ImmutableRecapRevisionError, RecapRevision
from app.transcription.models import Transcript
from sqlalchemy import select

from tests.conversations.conftest import login


async def _create_conversation(client, headers, org_id: str) -> str:  # noqa: ANN001
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Visit 1", "organization_id": org_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _seed_document(sessionmaker, conversation_id: str) -> None:  # noqa: ANN001
    """Directly inserts a minimal composed Document — real compose_document
    requires a fully processed conversation (source audio, transcript,
    facts; see tests/documents/_seed.py for that heavier setup), which
    these tests don't need: they exercise the Recap layer, not Document
    composition itself."""
    async with sessionmaker() as session:
        document = Document(
            conversation_id=uuid.UUID(conversation_id),
            status=DocumentRevisionStatus.READY_FOR_APPROVAL.value,
        )
        session.add(document)
        await session.flush()
        revision = DocumentRevision(
            document_id=document.id,
            revision_number=1,
            structured_content=[
                {
                    "category": "general_fact",
                    "title": "Allgemein",
                    "statements": [{"text": "Der Termin wurde besprochen.", "fact_ids": []}],
                }
            ],
            rendered_text="## Allgemein\n- Der Termin wurde besprochen.",
            status=DocumentRevisionStatus.READY_FOR_APPROVAL.value,
            blocking_issue_ids=[],
        )
        session.add(revision)
        await session.flush()
        document.current_revision_id = revision.id
        await session.commit()


async def test_generate_requires_composed_document(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers
    )
    assert response.status_code == 409
    assert "document" in response.json()["detail"]


async def test_generate_approve_export_recap(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)

    generate_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers
    )
    assert generate_response.status_code == 200, generate_response.text
    recap = generate_response.json()
    assert recap["status"] == "draft"
    assert recap["current_revision"]["status"] == "draft"
    assert recap["current_revision"]["revision_number"] == 1
    assert recap["current_revision"]["provider"] == "fake"
    assert recap["current_revision"]["content"]

    # Exporting before approval is refused.
    early_export = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap/export", headers=headers
    )
    assert early_export.status_code == 409

    admin_headers = await login(client, "carol", "yet another strong pw 789")
    approve_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/approve", headers=admin_headers
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["current_revision"]["approved_by_user_id"] is not None

    export_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap/export", headers=headers
    )
    assert export_response.status_code == 200
    assert export_response.text == recap["current_revision"]["content"]

    # Post-GA P0-2: DOCX/PDF exports too, with status/revision visible
    # (the plain-text export above deliberately stays byte-identical to
    # its pre-P0-2 shape).
    docx_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap/export?format=docx", headers=headers
    )
    assert docx_response.status_code == 200, docx_response.text
    assert docx_response.content[:2] == b"PK"

    pdf_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap/export?format=pdf", headers=headers
    )
    assert pdf_response.status_code == 200, pdf_response.text
    assert pdf_response.content[:4] == b"%PDF"

    # Re-generating adds a NEW revision — never mutates the approved one.
    headers = await login(client, "alice", "a very strong password 123")
    regenerate_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers
    )
    assert regenerate_response.status_code == 200
    new_recap = regenerate_response.json()
    assert new_recap["status"] == "draft"
    assert new_recap["current_revision"]["revision_number"] == 2


async def test_approved_recap_revision_is_immutable(client, seeded, app_env) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await client.post(f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers)
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/approve", headers=admin_headers
    )

    async with sessionmaker() as session:
        revision = (
            await session.execute(select(RecapRevision).where(RecapRevision.status == "approved"))
        ).scalar_one()
        revision.content = "tampered"
        with pytest.raises(ImmutableRecapRevisionError):
            await session.flush()


async def test_cross_organization_recap_isolation(client, seeded, app_env) -> None:  # noqa: ANN001
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _create_conversation(client, alice_headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)
    await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/generate", headers=alice_headers
    )

    bob_headers = await login(client, "bob", "another very strong pw 456")
    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/recap", headers=bob_headers
    )
    assert response.status_code == 404


async def test_generate_uses_active_transcript_language_after_reprocessing(
    client, seeded, app_env  # noqa: ANN001
) -> None:
    """Regression test: non-destructive reprocessing (app.transcription)
    keeps a prior Transcript row around instead of deleting it, so a
    conversation can have more than one. A naive `scalar_one_or_none()`
    query for "the" transcript raises MultipleResultsFound in that case —
    caught live in the browser, not by the other tests here, since they
    never seed more than one Transcript row."""
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await _create_conversation(client, headers, seeded["org_a"])
    _, sessionmaker = app_env
    await _seed_document(sessionmaker, conversation_id)

    async with sessionmaker() as session:
        media = MediaAsset(
            conversation_id=uuid.UUID(conversation_id),
            kind="source_audio",
            source_type="file_upload",
            storage_key="test/audio.wav",
            content_type="audio/wav",
            size_bytes=1024,
            sha256="0" * 64,
        )
        session.add(media)
        await session.flush()
        session.add_all(
            [
                Transcript(
                    conversation_id=uuid.UUID(conversation_id),
                    source_media_id=media.id,
                    language="en",
                    status="ready",
                    provider="fake",
                    model="fake-stt",
                    is_active=False,
                ),
                Transcript(
                    conversation_id=uuid.UUID(conversation_id),
                    source_media_id=media.id,
                    language="de",
                    status="ready",
                    provider="fake",
                    model="fake-stt",
                    is_active=True,
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/recap/generate", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_revision"]["language"] == "de"
