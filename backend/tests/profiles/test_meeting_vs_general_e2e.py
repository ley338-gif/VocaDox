"""The Phase 6 merge-gate proof: General and Meeting Processing Profiles
are genuinely different and both work end-to-end for real — create
conversation with each profile -> transcribe -> extract -> compose, and
the Meeting profile's output is meaningfully different in structure from
General's, not a relabeled copy. No real LLM/GPU required (a deterministic
stub provider), matching every prior phase's CI-never-requires-a-real-
model precedent.
"""

from __future__ import annotations

import json
from typing import Any

from app.processing.queues import EXTRACTION_WORKER_JOB_TYPES
from app.providers.llm import LLMProvider, LLMResponse
from app.workers.processing_worker import ProcessingWorker

from tests.conversations.conftest import login
from tests.profiles.conftest import create_conversation_with_source_audio, run_all_jobs


class _CategoryAwareStubProvider(LLMProvider):
    """Returns crafted, schema-shaped JSON keyed off whichever category's
    dynamically-built schema was actually requested (identified by which
    known item-field key appears in the JSON Schema's properties) —
    deterministic, no real inference, proves the template-driven schema
    each category gets is genuinely different per template."""

    _RESPONSES: dict[str, list[dict[str, Any]]] = {
        "facts": [
            {
                "subject": "Project X",
                "attribute": "status",
                "value": "on track",
                "certainty": "stated",
                "evidence_segment_sequences": [1],
            }
        ],
        "tasks": [],
        "topics": [
            {
                "topic": "Budget",
                "summary": "Discussed Q3 budget overrun",
                "outcome": "NOT_MENTIONED",
                "certainty": "stated",
                "evidence_segment_sequences": [1],
            }
        ],
        "action_items": [
            {
                "description": "Send the report",
                "owner": "John",
                "due_date": "Monday",
                "priority": "high",
                "certainty": "stated",
                "evidence_segment_sequences": [1],
            }
        ],
        # "decisions" is shared by both general and meeting's schema (each
        # with a different item shape) — always return a payload valid
        # against BOTH (meeting's schema additionally accepts, but does not
        # require, "rationale").
        "decisions": [
            {
                "description": "Ship on Friday",
                "decided_by": "Team",
                # "rationale" is required by meeting's dynamic decision
                # schema but simply ignored (extra field) by general's
                # builtin DecisionItem — one payload validates against both.
                "rationale": "Customer deadline",
                "certainty": "stated",
                "evidence_segment_sequences": [1],
            }
        ],
    }

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(text="", model_name="stub")

    async def complete_structured(
        self,
        prompt: str,
        *,
        json_schema: dict[str, Any],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        props = json_schema.get("properties", {})
        for key, items in self._RESPONSES.items():
            if key in props:
                return LLMResponse(text=json.dumps({key: items}), model_name="stub")
        raise AssertionError(f"unrecognized schema: {json_schema}")

    def status(self):
        from app.providers.llm import LLMProviderStatus

        return LLMProviderStatus(
            provider="stub",
            model="stub-category-aware-v1",
            model_revision=None,
            installed=True,
            device="cpu",
            structured_output=True,
        )


async def _create_ready_conversation(
    client, headers, org_id, processing_env, *, processing_profile_id: str | None
) -> str:
    _, sessionmaker, queue, storage = processing_env
    conversation_id, _media_id = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id, processing_profile_id=processing_profile_id
    )
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text
    await run_all_jobs(sessionmaker, queue, storage)
    return conversation_id


async def _run_extraction_with_stub_provider(sessionmaker, queue, storage) -> None:
    """`run_all_jobs` always wires the extraction worker to the fake
    provider that deliberately extracts nothing (see app.providers.llm's
    module docstring) — this test needs real, category-shaped output to
    prove General vs Meeting differ, so it drives its own extraction
    worker against `_CategoryAwareStubProvider` instead."""
    worker = ProcessingWorker(
        worker_id="test-extraction-stub",
        job_types=EXTRACTION_WORKER_JOB_TYPES,
        sessionmaker=sessionmaker,
        queue=queue,
        storage=storage,
        llm_provider=_CategoryAwareStubProvider(),
    )
    from app.processing.models import OutboxStatus, ProcessingOutbox
    from sqlalchemy import select

    for _ in range(10):
        async with sessionmaker() as session:
            outstanding_outbox = (
                await session.execute(
                    select(ProcessingOutbox.id).where(
                        ProcessingOutbox.status == OutboxStatus.PENDING.value
                    )
                )
            ).scalars().first()
        pending = await queue.queue_length("vocadox:processing:extract")
        if pending == 0 and outstanding_outbox is None:
            break
        await worker.run_forever(max_iterations=1)


async def test_general_and_meeting_profiles_produce_structurally_different_documents(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")

    profiles_resp = await client.get("/api/v1/processing-profiles", headers=headers)
    assert profiles_resp.status_code == 200
    by_key = {p["key"]: p for p in profiles_resp.json()}
    meeting_profile_id = by_key["meeting"]["id"]

    # General (no processing_profile_id -> SYSTEM DEFAULT layer applies).
    general_conv_id = await _create_ready_conversation(
        client, headers, seeded["org_a"], processing_env, processing_profile_id=None
    )
    # Meeting (explicit PROCESSING PROFILE layer).
    meeting_conv_id = await _create_ready_conversation(
        client, headers, seeded["org_a"], processing_env, processing_profile_id=meeting_profile_id
    )

    _, sessionmaker, queue, storage = processing_env
    for conv_id in (general_conv_id, meeting_conv_id):
        resp = await client.post(
            f"/api/v1/conversations/{conv_id}/process/extract", json={}, headers=headers
        )
        assert resp.status_code == 202, resp.text
    await _run_extraction_with_stub_provider(sessionmaker, queue, storage)

    general_facts = (
        await client.get(f"/api/v1/conversations/{general_conv_id}/facts", headers=headers)
    ).json()
    meeting_facts = (
        await client.get(f"/api/v1/conversations/{meeting_conv_id}/facts", headers=headers)
    ).json()
    general_categories = {f["category"] for f in general_facts}
    meeting_categories = {f["category"] for f in meeting_facts}

    assert general_categories, "general extraction produced no facts to compare"
    assert meeting_categories, "meeting extraction produced no facts to compare"
    assert general_categories != meeting_categories
    assert "agenda_topic" in meeting_categories
    assert "agenda_topic" not in general_categories
    assert general_categories == {"general_fact", "decision"}
    assert meeting_categories == {"agenda_topic", "decision", "action_item"}

    for conv_id in (general_conv_id, meeting_conv_id):
        resp = await client.post(
            f"/api/v1/conversations/{conv_id}/document/compose", json={}, headers=headers
        )
        assert resp.status_code == 200, resp.text

    general_doc = (
        await client.get(f"/api/v1/conversations/{general_conv_id}/document", headers=headers)
    ).json()
    meeting_doc = (
        await client.get(f"/api/v1/conversations/{meeting_conv_id}/document", headers=headers)
    ).json()

    general_titles = {s["title"] for s in general_doc["current_revision"]["structured_content"]}
    meeting_titles = {s["title"] for s in meeting_doc["current_revision"]["structured_content"]}
    assert general_titles != meeting_titles
    assert "Agenda & Discussion" in meeting_titles
    assert "Agenda & Discussion" not in general_titles

    # Every ProcessingRun/DocumentRevision recorded which template version
    # was actually used (spec §43's reproducibility requirement) — the two
    # conversations' revisions reference DIFFERENT template versions.
    assert (
        general_doc["current_revision"]["template_version_id"]
        != meeting_doc["current_revision"]["template_version_id"]
    )


async def test_effective_config_shows_processing_profile_layer_for_meeting_conversation(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    profiles_resp = await client.get("/api/v1/processing-profiles", headers=headers)
    by_key = {p["key"]: p for p in profiles_resp.json()}
    meeting_profile_id = by_key["meeting"]["id"]

    conv_id = await _create_ready_conversation(
        client, headers, seeded["org_a"], processing_env, processing_profile_id=None
    )

    # No profile selected -> every field resolved by SYSTEM DEFAULT.
    effective = (
        await client.get(f"/api/v1/conversations/{conv_id}/effective-config", headers=headers)
    ).json()
    sources = {f["field"]: f["source"] for f in effective["fields"]}
    assert sources["template_id"] == "system_default"

    versions_resp = await client.get(
        f"/api/v1/processing-profiles/{meeting_profile_id}/versions", headers=headers
    )
    meeting_version = versions_resp.json()[0]

    # Set the CONVERSATION OVERRIDE layer directly to the meeting
    # template's ids (spec §20's third layer), and confirm the
    # explainability surface correctly attributes the change to
    # "conversation_override", not silently to "processing_profile"/
    # "system_default".
    override_resp = await client.patch(
        f"/api/v1/conversations/{conv_id}/config-override",
        json={
            "template_id": meeting_version["template_id"],
            "template_version_id": meeting_version["template_version_id"],
        },
        headers=headers,
    )
    assert override_resp.status_code == 200

    effective_after = (
        await client.get(f"/api/v1/conversations/{conv_id}/effective-config", headers=headers)
    ).json()
    sources_after = {f["field"]: f["source"] for f in effective_after["fields"]}
    values_after = {f["field"]: f["value"] for f in effective_after["fields"]}
    assert sources_after["template_id"] == "conversation_override"
    assert values_after["template_id"] == meeting_version["template_id"]
    # Untouched fields still resolve from the (lower) system-default layer.
    assert sources_after["language"] == "system_default"
