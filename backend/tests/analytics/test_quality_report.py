"""Post-GA P1-4: the Evaluation Lab's customer-facing quality report —
real Word Error Rate + extraction-quality metrics over an explicitly
named sample of conversations, exportable as JSON/PDF/DOCX.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.analytics.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


async def test_quality_report_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report",
        json={"conversation_ids": ["00000000-0000-0000-0000-000000000001"]},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_quality_report_rejects_more_than_twenty_conversations(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    ids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(21)]
    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report",
        json={"conversation_ids": ids},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_quality_report_skips_nonexistent_conversation(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report",
        json={"conversation_ids": ["00000000-0000-0000-0000-000000000001"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conversation_results"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "conversation not found"
    assert body["mean_word_error_rate"] is None


async def test_quality_report_end_to_end_json(
    client: AsyncClient, seeded, processing_env  # noqa: ANN001
) -> None:
    """FakeSpeechProvider is deterministic — the same audio produces the
    same transcript both at initial processing and again when the report
    re-runs it, so Word Error Rate against the (uncorrected, still equal)
    ground truth comes out exactly 0.0. This proves the plumbing, same
    "no real model needed in CI" precedent every other Evaluation Lab
    test uses."""
    headers = await login(client, "carol", "yet another strong pw 789")
    _, sessionmaker, queue, storage = processing_env
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report",
        json={"conversation_ids": [conversation_id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] == []
    assert len(body["conversation_results"]) == 1
    assert body["conversation_results"][0]["conversation_id"] == conversation_id
    assert body["conversation_results"][0]["word_error_rate"] == 0.0
    assert body["mean_word_error_rate"] == 0.0
    assert body["speech_provider"] == "fake"
    assert body["quality_metrics"]["transcript_segments_total"] > 0


async def test_quality_report_pdf_export(
    client: AsyncClient, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    _, sessionmaker, queue, storage = processing_env
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report?format=pdf",
        json={"conversation_ids": [conversation_id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


async def test_quality_report_docx_export(
    client: AsyncClient, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    _, sessionmaker, queue, storage = processing_env
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202
    await run_all_jobs(sessionmaker, queue, storage)

    resp = await client.post(
        "/api/v1/admin/evaluation/quality-report?format=docx",
        json={"conversation_ids": [conversation_id]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"PK")
