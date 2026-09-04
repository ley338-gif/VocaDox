"""Evaluation Lab (spec §50): POST /admin/evaluation/model-comparison and
/prompt-comparison actually run the real fixture (app.analytics.fixtures)
through two real subjects and store real measured results — never a
mockup. CI uses `provider="fake"` ModelProfile rows (FakeLLMProvider is
deterministic and requires no external model), so these tests verify the
MECHANISM end-to-end deterministically; the actual two-DIFFERENT-real-
model (Ollama qwen2.5:14b vs qwen3:14b) comparison run for the validation
report's real numbers is documented separately (not run in CI, which has
no GPU/Ollama available) — see PHASE_8_VALIDATION_REPORT.md."""

from __future__ import annotations

from httpx import AsyncClient

from tests.analytics.conftest import login


async def _create_model_profile(client: AsyncClient, headers: dict[str, str], *, name: str) -> str:
    resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": name,
            "purpose": "extraction",
            "provider": "fake",
            "model_identifier": "fake-llm-v0",
            "temperature": 0.0,
            "max_tokens": 512,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_model_comparison_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/evaluation/model-comparison",
        json={
            "model_profile_id_a": "00000000-0000-0000-0000-000000000001",
            "model_profile_id_b": "00000000-0000-0000-0000-000000000002",
        },
        headers=headers,
    )
    assert resp.status_code == 403


async def test_model_comparison_rejects_identical_ids(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers, name="A")
    resp = await client.post(
        "/api/v1/admin/evaluation/model-comparison",
        json={"model_profile_id_a": profile_id, "model_profile_id_b": profile_id},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_model_comparison_404_on_unknown_profile(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers, name="A")
    resp = await client.post(
        "/api/v1/admin/evaluation/model-comparison",
        json={
            "model_profile_id_a": profile_id,
            "model_profile_id_b": "00000000-0000-0000-0000-000000000000",
        },
        headers=headers,
    )
    assert resp.status_code == 404


async def test_model_comparison_runs_real_metrics_and_is_listable(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_a = await _create_model_profile(client, headers, name="Model A (temp 0.0)")
    profile_b = await _create_model_profile(client, headers, name="Model B (temp 0.7)")

    resp = await client.post(
        "/api/v1/admin/evaluation/model-comparison",
        json={"model_profile_id_a": profile_a, "model_profile_id_b": profile_b},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["run_type"] == "model_comparison"
    assert run["status"] == "completed"
    assert run["subject_a"]["kind"] == "model_profile"
    for result in (run["result_a"], run["result_b"]):
        assert result["facts_expected"] == 4  # 2 general_fact + 1 decision + 1 task
        assert result["json_total_categories"] == 3
        assert result["latency_seconds"] >= 0
        # FakeLLMProvider deterministically returns empty-but-schema-valid
        # output -> 0 facts matched, all 3 categories JSON-valid.
        assert result["facts_matched"] == 0
        assert result["json_valid_categories"] == 3
    # Structurally counts/labels only, never actual fixture transcript
    # sentence text (the fixture's own KEY, e.g. "consultation_ramipril_v1",
    # is a harmless label and is fine to appear).
    body_text = resp.text.lower()
    assert "verschreibe" not in body_text
    assert "blutuntersuchung" not in body_text

    run_id = run["id"]
    get_resp = await client.get(f"/api/v1/admin/evaluation/runs/{run_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id

    list_resp = await client.get("/api/v1/admin/evaluation/runs", headers=headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == run_id for item in list_resp.json()["items"])


async def test_prompt_comparison_runs_real_metrics(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    profile_id = await _create_model_profile(client, headers, name="Shared model")

    def _category_instructions(wording: str) -> dict[str, str]:
        return {
            "general_fact": f"Extract general facts ({wording}).",
            "decision": f"Extract decisions ({wording}).",
            "task": f"Extract tasks ({wording}).",
        }

    prompt_resp = await client.post(
        "/api/v1/prompts",
        json={
            "key": "eval-test-prompt",
            "name": "Eval Test Prompt",
            "purpose": "extraction",
            "system_prompt": "You are a structured information extraction system.",
            "category_instructions": _category_instructions("baseline instructions"),
        },
        headers=headers,
    )
    assert prompt_resp.status_code == 201, prompt_resp.text
    prompt_id = prompt_resp.json()["id"]

    list_resp = await client.get(f"/api/v1/prompts/{prompt_id}/versions", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    versions = [list_resp.json()[0]["id"]]

    v_resp = await client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        json={
            "system_prompt": "You are a structured information extraction system.",
            "category_instructions": _category_instructions(
                "stricter instructions requiring evidence"
            ),
        },
        headers=headers,
    )
    assert v_resp.status_code == 201, v_resp.text
    versions.append(v_resp.json()["id"])

    resp = await client.post(
        "/api/v1/admin/evaluation/prompt-comparison",
        json={
            "prompt_version_id_a": versions[0],
            "prompt_version_id_b": versions[1],
            "model_profile_id": profile_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["run_type"] == "prompt_comparison"
    assert run["status"] == "completed"
    assert run["subject_a"]["kind"] == "prompt_version"
    assert run["result_a"]["facts_expected"] == 4
