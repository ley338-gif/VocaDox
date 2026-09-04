"""Prompt lifecycle tests (spec §43: DRAFT -> TEST -> PUBLISHED -> RETIRED,
never overwrite a published prompt)."""

from __future__ import annotations

from tests.conversations.conftest import login


async def test_seeded_prompts_exist_and_general_is_published(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/prompts", headers=headers)
    assert resp.status_code == 200
    by_key = {p["key"]: p for p in resp.json()}
    assert "extraction-general" in by_key
    assert "extraction-meeting" in by_key
    assert by_key["extraction-general"]["current_published_version_id"] is not None


async def test_prompt_version_lifecycle_never_overwrites_published(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/prompts",
        json={
            "key": "test-prompt",
            "name": "Test Prompt",
            "purpose": "extraction",
            "system_prompt": "v1 system prompt",
            "category_instructions": {"general_fact": "v1 instruction"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    prompt = create_resp.json()

    versions = (
        await client.get(f"/api/v1/prompts/{prompt['id']}/versions", headers=headers)
    ).json()
    v1 = versions[0]
    assert v1["status"] == "draft"

    publish_resp = await client.post(
        f"/api/v1/prompts/{prompt['id']}/versions/{v1['id']}/publish", headers=headers
    )
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "published"

    v2_resp = await client.post(
        f"/api/v1/prompts/{prompt['id']}/versions",
        json={
            "system_prompt": "v2 system prompt — completely different wording",
            "category_instructions": {"general_fact": "v2 instruction"},
        },
        headers=headers,
    )
    assert v2_resp.status_code == 201
    v2 = v2_resp.json()
    assert v2["version_number"] == 2
    assert v2["status"] == "draft"

    await client.post(
        f"/api/v1/prompts/{prompt['id']}/versions/{v2['id']}/publish", headers=headers
    )

    versions_after = (
        await client.get(f"/api/v1/prompts/{prompt['id']}/versions", headers=headers)
    ).json()
    v1_after = next(v for v in versions_after if v["id"] == v1["id"])
    assert v1_after["status"] == "retired"
    # The retired version's content is exactly what was published — never
    # silently rewritten to match v2.
    assert v1_after["system_prompt"] == "v1 system prompt"

    prompt_after = (await client.get(f"/api/v1/prompts/{prompt['id']}", headers=headers)).json()
    assert prompt_after["current_published_version_id"] == v2["id"]
