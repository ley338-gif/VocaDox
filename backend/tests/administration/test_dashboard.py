"""Admin Portal Dashboard (spec §49): real, live-checked component health
— never a fabricated "Healthy" — real queue counts, and the hard privacy
rule that no conversation/fact/transcript/document content ever appears
here."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_dashboard_requires_system_admin(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert resp.status_code == 403


async def test_dashboard_shows_real_component_health_and_queue_counts(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    component_names = {c["name"] for c in body["components"]}
    assert component_names == {
        "api",
        "postgresql",
        "valkey",
        "speech_provider",
        "diarization_provider",
        "llm_provider",
    }
    # The fake speech/diarization/llm providers CI/tests always run with
    # report installed=True — never a fabricated "Healthy" for a real
    # provider that isn't actually configured.
    speech = next(c for c in body["components"] if c["name"] == "speech_provider")
    assert speech["healthy"] is True

    assert set(body["queue"].keys()) == {"queued", "running", "failed"}
    assert all(isinstance(v, int) for v in body["queue"].values())
    assert body["application_version"]

    # Hard privacy rule: the dashboard schema itself has no field capable
    # of carrying conversation/fact/transcript/document content — verified
    # here by checking the actual response only ever contains the fixed
    # component/queue/hardware/version keys, never conversation-shaped data.
    assert set(body.keys()) == {"components", "queue", "hardware", "application_version"}
