"""Template Engine tests (spec §42): real versioning (never mutate a
published version in place, publishing retires-not-deletes the prior
version), the seeded "general"/"meeting" templates, and RBAC enforcement
on the admin surface."""

from __future__ import annotations

import uuid as _uuid

import pytest
from app.templates.models import ImmutablePublishedVersionError, TemplateVersion

from tests.conversations.conftest import login


async def test_general_and_meeting_seeded_and_published(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/templates", headers=headers)
    assert resp.status_code == 200
    by_key = {t["key"]: t for t in resp.json()}
    assert set(by_key) == {"general", "meeting", "medical_consultation", "psychotherapy"}
    assert by_key["general"]["current_published_version_id"] is not None
    assert by_key["meeting"]["current_published_version_id"] is not None
    # post-GA: medical_consultation is now a real, selectable, published
    # "letter" layout (see app.templates.seed's module docstring).
    # psychotherapy remains a foundation-only template (spec: "prepared as
    # foundation only") -- deliberately NOT published/selectable yet.
    assert by_key["medical_consultation"]["current_published_version_id"] is not None
    assert by_key["psychotherapy"]["current_published_version_id"] is None


async def test_meeting_categories_are_genuinely_different_from_general(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    by_key = {t["key"]: t for t in templates}

    general_versions = (
        await client.get(f"/api/v1/templates/{by_key['general']['id']}/versions", headers=headers)
    ).json()
    meeting_versions = (
        await client.get(f"/api/v1/templates/{by_key['meeting']['id']}/versions", headers=headers)
    ).json()
    general_categories = {c["key"] for c in general_versions[0]["extraction_categories"]}
    meeting_categories = {c["key"] for c in meeting_versions[0]["extraction_categories"]}

    assert general_categories == {"general_fact", "decision", "task"}
    # Not a relabeled copy: meeting has an entirely new category
    # (agenda_topic) and its own "action_item" replacing "task".
    assert meeting_categories == {"agenda_topic", "decision", "action_item"}
    assert general_categories != meeting_categories

    # The general template reuses the exact Phase 4/5 builtin schemas.
    assert all(c.get("builtin") for c in general_versions[0]["extraction_categories"])
    # Meeting's categories are genuinely template-defined (not builtin),
    # each with their own field list distinct from general's.
    meeting_action_item = next(
        c for c in meeting_versions[0]["extraction_categories"] if c["key"] == "action_item"
    )
    assert not meeting_action_item.get("builtin")
    assert {f["name"] for f in meeting_action_item["fields"]} == {
        "description", "owner", "due_date", "priority",
    }


async def test_create_version_publish_never_mutates_prior_version(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": "test-template",
            "name": "Test Template",
            "description": "for versioning test",
            "extraction_categories": [{"key": "general_fact", "builtin": True}],
            "presentation": [{"category": "general_fact", "title": "Facts"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    template = create_resp.json()
    assert template["current_published_version_id"] is None  # draft only, not yet published

    versions_resp = await client.get(
        f"/api/v1/templates/{template['id']}/versions", headers=headers
    )
    v1 = versions_resp.json()[0]
    assert v1["version_number"] == 1
    assert v1["status"] == "draft"

    publish_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions/{v1['id']}/publish", headers=headers
    )
    assert publish_resp.status_code == 200
    published_v1 = publish_resp.json()
    assert published_v1["status"] == "published"
    assert published_v1["published_at"] is not None

    # Create and publish v2 with genuinely different content.
    v2_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions",
        json={
            "extraction_categories": [{"key": "decision", "builtin": True}],
            "presentation": [{"category": "decision", "title": "Decisions"}],
        },
        headers=headers,
    )
    assert v2_resp.status_code == 201
    v2 = v2_resp.json()
    assert v2["version_number"] == 2

    publish_v2_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions/{v2['id']}/publish", headers=headers
    )
    assert publish_v2_resp.status_code == 200

    # The old v1 is RETIRED, never deleted, and its content is unchanged.
    versions_after = (
        await client.get(f"/api/v1/templates/{template['id']}/versions", headers=headers)
    ).json()
    v1_after = next(v for v in versions_after if v["id"] == v1["id"])
    assert v1_after["status"] == "retired"
    assert v1_after["extraction_categories"] == v1["extraction_categories"]

    template_after = (
        await client.get(f"/api/v1/templates/{template['id']}", headers=headers)
    ).json()
    assert template_after["current_published_version_id"] == v2["id"]


async def test_template_organization_can_be_tagged_and_reassigned(client, seeded) -> None:  # noqa: ANN001
    """post-GA: light org-scoping (see app.templates.router's docstring) —
    a template can be created global (organization_id omitted/None), tagged
    to an organization at creation, and reassigned/cleared afterward via
    `PATCH /{template_id}` — a plain metadata edit, not a versioned content
    change."""
    headers = await login(client, "carol", "yet another strong pw 789")

    global_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": "test-global-template",
            "name": "Global Template",
            "extraction_categories": [{"key": "general_fact", "builtin": True}],
            "presentation": [{"category": "general_fact", "title": "Facts"}],
        },
        headers=headers,
    )
    assert global_resp.status_code == 201, global_resp.text
    assert global_resp.json()["organization_id"] is None

    org_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": "test-org-template",
            "name": "Org Template",
            "organization_id": seeded["org_a"],
            "extraction_categories": [{"key": "general_fact", "builtin": True}],
            "presentation": [{"category": "general_fact", "title": "Facts"}],
        },
        headers=headers,
    )
    assert org_resp.status_code == 201, org_resp.text
    org_template = org_resp.json()
    assert org_template["organization_id"] == seeded["org_a"]

    reassign_resp = await client.patch(
        f"/api/v1/templates/{org_template['id']}",
        json={"organization_id": seeded["org_b"]},
        headers=headers,
    )
    assert reassign_resp.status_code == 200, reassign_resp.text
    assert reassign_resp.json()["organization_id"] == seeded["org_b"]

    clear_resp = await client.patch(
        f"/api/v1/templates/{org_template['id']}",
        json={"organization_id": None},
        headers=headers,
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["organization_id"] is None


async def test_published_template_version_content_is_immutable_at_orm_level(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Real, ORM-enforced immutability for the two newest content columns
    (`document_body`/`letterhead_logo_asset_key`) — mirrors
    `tests/documents/test_approval_and_immutability.py`'s pattern of
    attempting a real mutation and confirming it's rejected, not merely
    "no route happens to call update.\""""
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": "test-immutable-freeform",
            "name": "Test Immutable Freeform",
            "extraction_categories": [{"key": "decision", "builtin": True}],
            "presentation": [{"category": "decision", "title": "Decisions"}],
            "document_layout": "freeform",
            "document_body": "Original: [decision_1]",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    template = create_resp.json()
    versions_resp = await client.get(
        f"/api/v1/templates/{template['id']}/versions", headers=headers
    )
    v1 = versions_resp.json()[0]
    publish_resp = await client.post(
        f"/api/v1/templates/{template['id']}/versions/{v1['id']}/publish", headers=headers
    )
    assert publish_resp.status_code == 200, publish_resp.text

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        version = await session.get(TemplateVersion, _uuid.UUID(v1["id"]))
        assert version is not None
        version.document_body = "TAMPERED"
        with pytest.raises(ImmutablePublishedVersionError):
            await session.flush()
        await session.rollback()

    async with sessionmaker() as session:
        version = await session.get(TemplateVersion, _uuid.UUID(v1["id"]))
        assert version is not None
        version.letterhead_logo_asset_key = "tampered/key"
        with pytest.raises(ImmutablePublishedVersionError):
            await session.flush()
        await session.rollback()


async def test_template_write_requires_permission(client, seeded) -> None:  # noqa: ANN001
    # alice only has template:read (standard User role), not template:write.
    headers = await login(client, "alice", "a very strong password 123")
    read_resp = await client.get("/api/v1/templates", headers=headers)
    assert read_resp.status_code == 200

    write_resp = await client.post(
        "/api/v1/templates",
        json={
            "key": "should-fail",
            "name": "x",
            "extraction_categories": [],
            "presentation": [],
        },
        headers=headers,
    )
    assert write_resp.status_code == 403
