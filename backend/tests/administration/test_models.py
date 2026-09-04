"""Admin Portal Models/Speech/Diarization surface: aggregates the three
existing provider `.status()` checks (Phase 3/4) into one page's data —
gated by the pre-existing `provider:read` permission."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_models_overview_requires_provider_read(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/models", headers=headers)
    assert resp.status_code == 403


async def test_models_overview_shows_real_provider_status(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/models", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["speech"]["provider"] == "fake"
    assert body["diarization"]["provider"] == "fake"
    assert body["llm"]["provider"] == "fake"
    assert body["llm"]["installed"] is True


async def test_llm_provider_status_endpoint(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/providers/llm", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider"] == "fake"
