"""Model Lifecycle (spec §51): AVAILABLE -> TESTING -> PILOT -> PRODUCTION
-> RETIRED, with rollback to any earlier status. Every transition is an
explicit, permission-gated admin action recorded as a
`model_profile_lifecycle_events` row — never automatic."""

from __future__ import annotations

from httpx import AsyncClient

from tests.analytics.conftest import login

_CHECKLIST = {
    "license_check": True,
    "compatibility_check": True,
    "benchmark": True,
    "security_review": True,
    "admin_approval": True,
}


async def _create_model_profile(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": "Lifecycle test model",
            "purpose": "extraction",
            "provider": "fake",
            "model_identifier": "fake-llm-v0",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_lifecycle_transition_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, admin_headers)

    user_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "testing", "checklist": _CHECKLIST},
        headers=user_headers,
    )
    assert resp.status_code == 403


async def test_forward_transition_requires_complete_checklist(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers)

    resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "testing", "checklist": {"license_check": True}},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "checklist" in resp.json()["detail"]


async def test_cannot_skip_a_lifecycle_step(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers)

    # AVAILABLE -> PRODUCTION directly (skipping TESTING/PILOT) must be
    # rejected even with a complete checklist.
    resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "production", "checklist": _CHECKLIST},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_full_lifecycle_forward_and_rollback(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers)

    for to_status in ("testing", "pilot", "production"):
        resp = await client.post(
            f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
            json={
                "to_status": to_status,
                "checklist": _CHECKLIST,
                "note": f"promote to {to_status}",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["to_status"] == to_status
        assert resp.json()["is_rollback"] is False

    lifecycle = await client.get(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle", headers=headers
    )
    assert lifecycle.status_code == 200
    assert lifecycle.json()["lifecycle_status"] == "production"
    assert len(lifecycle.json()["events"]) == 3

    # Rollback PRODUCTION -> TESTING (skipping PILOT backward is fine —
    # rollback moves to ANY earlier status) — history is preserved, not
    # destroyed.
    rollback_resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "testing", "is_rollback": True, "note": "regression found"},
        headers=headers,
    )
    assert rollback_resp.status_code == 201, rollback_resp.text
    assert rollback_resp.json()["is_rollback"] is True
    assert rollback_resp.json()["from_status"] == "production"
    assert rollback_resp.json()["to_status"] == "testing"

    lifecycle = await client.get(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle", headers=headers
    )
    assert lifecycle.json()["lifecycle_status"] == "testing"
    # All 4 events (3 forward + 1 rollback) are still there — rollback
    # never deletes history.
    assert len(lifecycle.json()["events"]) == 4


async def test_rollback_cannot_move_forward(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers)

    resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "pilot", "is_rollback": True},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_reactivate_a_retired_profile_via_rollback(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers)

    for to_status in ("testing", "pilot", "production", "retired"):
        resp = await client.post(
            f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
            json={"to_status": to_status, "checklist": _CHECKLIST},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    # Reactivate a previously-retired profile back to AVAILABLE (spec:
    # "reactivating a previously-retired one — don't destroy history").
    resp = await client.post(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle-transition",
        json={"to_status": "available", "is_rollback": True, "note": "reactivated"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["to_status"] == "available"

    lifecycle = await client.get(
        f"/api/v1/admin/model-profiles/{profile_id}/lifecycle", headers=headers
    )
    assert lifecycle.json()["lifecycle_status"] == "available"
    assert len(lifecycle.json()["events"]) == 5
