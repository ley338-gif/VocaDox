"""API-level Timeline tests, centered on the phase's single most important
test: two different organizations that coincidentally use the same
`external_reference` string must NEVER have their conversations merged
into one timeline (see app.longitudinal.service's module docstring)."""

from __future__ import annotations

from httpx import AsyncClient

from tests.longitudinal.conftest import login  # noqa: F401


async def _create_conversation(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    organization_id: str,
    title: str,
    external_reference: str,
) -> str:
    resp = await client.post(
        "/api/v1/conversations",
        json={
            "title": title,
            "organization_id": organization_id,
            "external_reference": external_reference,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_timeline_groups_conversations_sharing_reference_within_one_org(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]

    await _create_conversation(
        client, headers, organization_id=org_a, title="Visit 1", external_reference="CASE-100"
    )
    await _create_conversation(
        client, headers, organization_id=org_a, title="Visit 2", external_reference="CASE-100"
    )
    # A decoy conversation with a different reference must not appear.
    await _create_conversation(
        client, headers, organization_id=org_a, title="Unrelated", external_reference="CASE-999"
    )

    resp = await client.get(
        f"/api/v1/external-references/CASE-100/timeline?organization_id={org_a}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["external_reference"] == "CASE-100"
    assert len(body["conversations"]) == 2
    titles = {c["title"] for c in body["conversations"]}
    assert titles == {"Visit 1", "Visit 2"}


async def test_cross_organization_same_reference_isolation(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    """THE critical test for this phase: Alice (Org A) and Bob (Org B) both
    use the reference "1" (e.g. both orgs numbering cases from scratch).
    Bob must never see Alice's conversation in his org's timeline for "1",
    and must be refused (not silently emptied) when he tries to view Org
    A's timeline directly."""
    org_a = seeded["org_a"]
    org_b = seeded["org_b"]

    # Sequential logins on one shared-cookie-jar client: do all of Alice's
    # actions before logging in as Bob (each login replaces the session
    # cookie) -- same convention as tests/conversations/test_api.py.
    alice_headers = await login(client, "alice", "a very strong password 123")
    await _create_conversation(
        client, alice_headers, organization_id=org_a, title="Org A Case 1",
        external_reference="1",
    )

    bob_headers = await login(client, "bob", "another very strong pw 456")
    await _create_conversation(
        client, bob_headers, organization_id=org_b, title="Org B Case 1",
        external_reference="1",
    )

    # Bob's own org's timeline for "1" must show ONLY Org B's conversation.
    resp = await client.get(
        f"/api/v1/external-references/1/timeline?organization_id={org_b}", headers=bob_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["conversations"]) == 1
    assert body["conversations"][0]["title"] == "Org B Case 1"
    # No leaked title, no leaked count inflation from Org A's same-named "1".

    # Bob attempting to view Org A's timeline directly is refused outright
    # (403 -- not a member of Org A), never silently returning an empty or
    # partial result that could be mistaken for "no data". (Still logged in
    # as Bob -- the session cookie belongs to whoever logged in last.)
    resp = await client.get(
        f"/api/v1/external-references/1/timeline?organization_id={org_a}", headers=bob_headers
    )
    assert resp.status_code == 403, resp.text

    # Symmetric check from Alice's side -- re-login as Alice so the shared
    # cookie jar's session actually belongs to her again (an X-CSRF-Token
    # header alone does not change who the session cookie authenticates as).
    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get(
        f"/api/v1/external-references/1/timeline?organization_id={org_a}", headers=alice_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["conversations"]) == 1
    assert body["conversations"][0]["title"] == "Org A Case 1"

    resp = await client.get(
        f"/api/v1/external-references/1/timeline?organization_id={org_b}", headers=alice_headers
    )
    assert resp.status_code == 403, resp.text


async def test_cross_organization_same_reference_isolation_in_comparison(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    """The same isolation guarantee must hold for the Comparison endpoint,
    not just the Timeline -- a naive implementation that queried
    `external_reference` alone anywhere in the comparison path would leak
    Org A's facts into Org B's comparison result."""
    org_a = seeded["org_a"]
    org_b = seeded["org_b"]

    alice_headers = await login(client, "alice", "a very strong password 123")
    await _create_conversation(
        client, alice_headers, organization_id=org_a, title="Org A Case 7", external_reference="7"
    )

    bob_headers = await login(client, "bob", "another very strong pw 456")
    await _create_conversation(
        client, bob_headers, organization_id=org_b, title="Org B Case 7", external_reference="7"
    )

    resp = await client.get(
        f"/api/v1/external-references/7/comparison?organization_id={org_b}", headers=bob_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["conversation_count"] == 1

    resp = await client.get(
        f"/api/v1/external-references/7/comparison?organization_id={org_a}", headers=bob_headers
    )
    assert resp.status_code == 403, resp.text


async def test_related_conversations_endpoint_from_a_specific_conversation(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]
    conv1 = await _create_conversation(
        client, headers, organization_id=org_a, title="Visit 1", external_reference="CASE-200"
    )
    await _create_conversation(
        client, headers, organization_id=org_a, title="Visit 2", external_reference="CASE-200"
    )

    resp = await client.get(f"/api/v1/conversations/{conv1}/related", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["conversations"]) == 2


async def test_related_conversations_with_no_external_reference_returns_self_only(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    org_a = seeded["org_a"]
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Solo conversation", "organization_id": org_a},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/conversations/{conv_id}/related", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["conversations"]) == 1
    assert body["conversations"][0]["conversation_id"] == conv_id
