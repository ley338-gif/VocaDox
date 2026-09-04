"""ModelProfile CRUD/versioning tests (spec §18): a real, admin-manageable,
versioned entity extending Phase 4's minimal foundation."""

from __future__ import annotations

from tests.conversations.conftest import login


async def test_seeded_extraction_profile_exists(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/model-profiles", headers=headers)
    assert resp.status_code == 200
    purposes = {p["purpose"] for p in resp.json()}
    assert "extraction" in purposes


async def test_update_model_profile_snapshots_prior_state_as_a_version(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": "Test Extraction Model",
            "purpose": "extraction",
            "provider": "fake",
            "model_identifier": "fake-llm-v0",
            "temperature": 0.1,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    profile = create_resp.json()
    assert profile["version"] == "1"

    update_resp = await client.patch(
        f"/api/v1/model-profiles/{profile['id']}",
        json={"temperature": 0.5, "thinking_mode": "extended"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["temperature"] == 0.5
    assert updated["thinking_mode"] == "extended"
    assert updated["version"] == "2"

    versions_resp = await client.get(
        f"/api/v1/model-profiles/{profile['id']}/versions", headers=headers
    )
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 2
    # v1 snapshot preserves the ORIGINAL (pre-edit) temperature — never
    # silently rewritten to match the edit.
    assert versions[0]["version_number"] == 1
    assert versions[0]["temperature"] == 0.1
    assert versions[1]["version_number"] == 2
    assert versions[1]["temperature"] == 0.5


async def test_model_profile_write_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": "x", "purpose": "extraction", "provider": "fake", "model_identifier": "y",
        },
        headers=headers,
    )
    assert resp.status_code == 403
