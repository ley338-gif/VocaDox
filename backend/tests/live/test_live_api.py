"""Post-GA P2-1: live transcript endpoints — ingest, read, clear.
FakeSpeechProvider is deterministic (ignores actual audio content), so
every chunk transcribes to the same fixed text; that's enough to prove
the plumbing (store replace, response shape, permission gate), same
precedent every other Fake-provider test in this project uses.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.live.conftest import login, make_wav_bytes


async def test_ingest_live_chunk_returns_transcript(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    files = {"file": ("chunk.wav", make_wav_bytes(), "audio/wav")}
    resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/live/chunks", files=files, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunk_count"] == 1
    assert "fake transcript segment" in body["transcript_text"]
    assert body["draft_text"] is None


async def test_get_live_session_reflects_latest_chunk(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    files = {"file": ("chunk.wav", make_wav_bytes(), "audio/wav")}
    await client.post(
        f"/api/v1/conversations/{conv['id']}/live/chunks", files=files, headers=headers
    )
    resp = await client.get(f"/api/v1/conversations/{conv['id']}/live", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["chunk_count"] == 1


async def test_get_live_session_empty_before_any_chunk(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    resp = await client.get(f"/api/v1/conversations/{conv['id']}/live", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunk_count"] == 0
    assert body["transcript_text"] == ""


async def test_clear_live_session(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    files = {"file": ("chunk.wav", make_wav_bytes(), "audio/wav")}
    await client.post(
        f"/api/v1/conversations/{conv['id']}/live/chunks", files=files, headers=headers
    )
    resp = await client.delete(f"/api/v1/conversations/{conv['id']}/live", headers=headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/conversations/{conv['id']}/live", headers=headers)
    assert resp.json()["chunk_count"] == 0


async def test_ingest_live_chunk_rejects_empty_file(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    files = {"file": ("chunk.wav", b"", "audio/wav")}
    resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/live/chunks", files=files, headers=headers
    )
    assert resp.status_code == 400


async def test_ingest_live_chunk_requires_permission(client: AsyncClient, seeded, app_env) -> None:  # noqa: ANN001
    """Auditor has no conversation:record permission."""
    import uuid as _uuid

    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

    headers = await login(client, "alice", "a very strong password 123")
    conv = (
        await client.post(
            "/api/v1/conversations",
            json={"title": "Live test", "organization_id": seeded["org_a"]},
            headers=headers,
        )
    ).json()

    _, sessionmaker = app_env

    async with sessionmaker() as session:
        auditor_role = await get_role_by_name(session, "Auditor")
        assert auditor_role is not None
        dana = await create_local_user(
            session, username="dana", password="a reasonably strong pw 000", display_name="Dana"
        )
        group = await get_or_create_group(session, name="Org A Auditors")
        await assign_role_to_group(session, group_id=group.id, role_id=auditor_role.id)
        await add_user_to_group(session, user_id=dana.id, group_id=group.id)
        session.add(
            OrganizationMembership(user_id=dana.id, organization_id=_uuid.UUID(seeded["org_a"]))
        )
        await session.commit()

    dana_headers = await login(client, "dana", "a reasonably strong pw 000")
    files = {"file": ("chunk.wav", make_wav_bytes(), "audio/wav")}
    resp = await client.post(
        f"/api/v1/conversations/{conv['id']}/live/chunks", files=files, headers=dana_headers
    )
    assert resp.status_code == 403
