"""Ask VocaDox (post-GA P1-1): every returned statement must cite a real,
currently-visible fact id -- an uncited, hallucinated-id, or malformed
statement is silently dropped, never surfaced. `FakeLLMProvider` (the
default in tests) always returns an empty answer, so the "citation
enforcement" itself is tested by calling `app.ask.service.ask` directly
with a stub provider, mirroring the `_StubLLMProvider` pattern already
used for extraction/document tests.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.providers.llm import LLMProvider, LLMResponse
from httpx import AsyncClient

from tests.ask.conftest import (
    make_ready_conversation_with_transcript,
    seed_facts_with_contradiction_and_clean_fact,
)
from tests.conversations.conftest import login


class _StubAskProvider(LLMProvider):
    def __init__(self, statements: list[dict[str, Any]]) -> None:
        self._statements = statements

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
        return LLMResponse(
            text=json.dumps({"statements": self._statements}), model_name="stub"
        )

    def status(self):  # pragma: no cover - not exercised
        raise NotImplementedError


async def test_ask_requires_permission(client: AsyncClient, seeded, processing_env) -> None:  # noqa: ANN001
    """Template Manager has neither fact:read nor ask:query."""
    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )

    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        role = await get_role_by_name(session, "Template Manager")
        assert role is not None
        user = await create_local_user(
            session, username="tmgr", password="a reasonably strong pw 111", display_name="T"
        )
        group = await get_or_create_group(session, name="Template Managers")
        await assign_role_to_group(session, group_id=group.id, role_id=role.id)
        await add_user_to_group(session, user_id=user.id, group_id=group.id)
        await session.commit()

    headers = await login(client, "tmgr", "a reasonably strong pw 111")
    resp = await client.post(
        "/api/v1/ask", json={"question": "Was wurde entschieden?"}, headers=headers
    )
    assert resp.status_code == 403


async def test_ask_with_no_evidence_returns_empty(
    client: AsyncClient, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/ask",
        json={"question": "Ein völlig unbekanntes Thema Zebraflunder?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["statements"] == []
    assert body["had_candidate_evidence"] is False


async def test_ask_discards_uncited_and_hallucinated_statements(
    client: AsyncClient, seeded, processing_env  # noqa: ANN001
) -> None:
    from app.ask.service import ask

    headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        fact_ids = await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )

    real_id = str(fact_ids["clean_fact_id"])
    fake_id = str(uuid.uuid4())
    provider = _StubAskProvider(
        [
            {"text": "Ein belegter Satz.", "fact_ids": [real_id]},
            {"text": "Unbelegte Behauptung.", "fact_ids": []},
            {"text": "Erfundener Beleg.", "fact_ids": [fake_id]},
        ]
    )

    async with sessionmaker() as session:
        result = await ask(
            session,
            # Must literally match the seeded clean fact's rendered content
            # ("Follow-up clinic — location: Building B, room 4") -- see
            # app.search.service's SQLite ILIKE fallback (ADR-0030): tests
            # exercise scoping/verification, not real semantic matching.
            question="Follow-up clinic",
            organization_ids={uuid.UUID(seeded["org_a"])},
            group_ids=None,
            conversation_id=None,
            provider=provider,
            asked_by_user_id=None,
        )
        await session.commit()

    assert len(result.answer_statements) == 1
    assert result.answer_statements[0]["text"] == "Ein belegter Satz."
    assert result.answer_statements[0]["fact_ids"] == [real_id]


async def test_ask_is_organization_scoped(client: AsyncClient, seeded, processing_env) -> None:  # noqa: ANN001
    alice_headers = await login(client, "alice", "a very strong password 123")
    conversation_id = await make_ready_conversation_with_transcript(
        client, alice_headers, seeded["org_a"], processing_env
    )
    _, sessionmaker, _queue, _storage = processing_env
    async with sessionmaker() as session:
        await seed_facts_with_contradiction_and_clean_fact(
            session, conversation_id=uuid.UUID(conversation_id)
        )

    bob_headers = await login(client, "bob", "another very strong pw 456")
    resp = await client.post("/api/v1/ask", json={"question": "Ramipril"}, headers=bob_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["statements"] == []
    assert resp.json()["had_candidate_evidence"] is False
