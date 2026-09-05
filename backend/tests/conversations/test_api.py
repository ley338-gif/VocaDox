"""End-to-end API tests for the conversation-capture domain: CRUD,
organization isolation, permission enforcement, media upload/download,
participants/markers/notes, deletion, and audit events."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conversations.conftest import login, make_wav_bytes


async def _create_conversation(
    client: AsyncClient, headers: dict, org_id: str, title: str = "Visit 1"
) -> dict:
    response = await client.post(
        "/api/v1/conversations",
        json={"title": title, "organization_id": org_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_get_conversation(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    assert conv["status"] == "created"
    assert conv["organization_id"] == seeded["org_a"]

    get_response = await client.get(f"/api/v1/conversations/{conv['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Visit 1"


async def test_cannot_create_conversation_in_foreign_organization(
    client: AsyncClient, seeded: dict
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Sneaky", "organization_id": seeded["org_b"]},
        headers=headers,
    )
    assert response.status_code == 403


async def test_cross_organization_uuid_guessing_is_denied(
    client: AsyncClient, seeded: dict
) -> None:
    """The mandatory hard-security-property test: User A/Org A creates a
    Conversation; User B/Org B attempts UUID access and is denied."""
    alice_headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, alice_headers, seeded["org_a"])

    # New client for bob so alice's session cookie isn't reused.
    bob_headers = await login(client, "bob", "another very strong pw 456")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=bob_headers)
    assert response.status_code == 404  # never 403 — must not confirm existence


async def test_system_admin_can_access_any_organization_conversation(
    client: AsyncClient, seeded: dict
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, alice_headers, seeded["org_a"])

    carol_headers = await login(client, "carol", "yet another strong pw 789")
    response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=carol_headers)
    assert response.status_code == 200


async def test_unauthenticated_request_is_denied(client: AsyncClient, seeded: dict) -> None:
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401


async def test_missing_permission_is_denied(client: AsyncClient, seeded: dict, app_env) -> None:
    app, sessionmaker = app_env
    from app.identity.service import create_local_user

    async with sessionmaker() as session:
        # A user with no group/role/permissions at all.
        await create_local_user(
            session,
            username="noperm",
            password="no permissions whatsoever 000",
            display_name="No Perm",
        )
        await session.commit()

    headers = await login(client, "noperm", "no permissions whatsoever 000")
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "x", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    assert response.status_code == 403


async def test_list_conversations_only_shows_own_organization(
    client: AsyncClient, seeded: dict
) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    await _create_conversation(client, alice_headers, seeded["org_a"], title="Alice's conv")

    # Query alice's list before bob logs in — the test client's cookie jar
    # holds one session at a time, and a later login overwrites it.
    alice_list = await client.get("/api/v1/conversations", headers=alice_headers)
    titles = [c["title"] for c in alice_list.json()["items"]]
    assert "Alice's conv" in titles
    assert "Bob's conv" not in titles

    bob_headers = await login(client, "bob", "another very strong pw 456")
    await _create_conversation(client, bob_headers, seeded["org_b"], title="Bob's conv")
    bob_list = await client.get("/api/v1/conversations", headers=bob_headers)
    bob_titles = [c["title"] for c in bob_list.json()["items"]]
    assert "Bob's conv" in bob_titles
    assert "Alice's conv" not in bob_titles


async def test_update_conversation(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    response = await client.patch(
        f"/api/v1/conversations/{conv['id']}", json={"title": "Renamed"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


async def test_upload_audio_transitions_conversation_to_uploaded(
    client: AsyncClient, seeded: dict
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])

    files = {"file": ("session.wav", make_wav_bytes(), "audio/wav")}
    response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    assert response.status_code == 201, response.text
    media = response.json()
    assert media["sha256"]
    assert media["kind"] == "source_audio"
    assert media["source_type"] == "file_upload"

    conv_after = await client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    assert conv_after.json()["status"] == "uploaded"


async def test_upload_empty_file_is_rejected(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    files = {"file": ("empty.wav", b"", "audio/wav")}
    response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    assert response.status_code == 422


async def test_upload_non_audio_file_is_rejected(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    files = {"file": ("evil.wav", b"<html><script>alert(1)</script></html>", "audio/wav")}
    response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    assert response.status_code == 422


async def test_malicious_filename_does_not_leak_into_storage_or_headers(
    client: AsyncClient, seeded: dict
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    malicious_name = '../../evil"\r\nX-Injected: yes.wav'
    files = {"file": (malicious_name, make_wav_bytes(), "audio/wav")}
    response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    assert response.status_code == 201
    media = response.json()
    assert ".." not in media.get("original_filename", "") or media["original_filename"] is None

    content_response = await client.get(
        f"/api/v1/conversations/{conv['id']}/media/{media['id']}/content", headers=headers
    )
    assert content_response.status_code == 200
    disposition = content_response.headers.get("content-disposition", "")
    assert "\r" not in disposition and "\n" not in disposition


async def test_media_download_and_sha256_roundtrip(client: AsyncClient, seeded: dict) -> None:
    import hashlib

    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    data = make_wav_bytes(duration_s=0.3)
    files = {"file": ("session.wav", data, "audio/wav")}
    upload_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    media = upload_response.json()
    assert media["sha256"] == hashlib.sha256(data).hexdigest()

    content_response = await client.get(
        f"/api/v1/conversations/{conv['id']}/media/{media['id']}/content", headers=headers
    )
    assert content_response.status_code == 200
    assert hashlib.sha256(content_response.content).hexdigest() == media["sha256"]


async def test_media_content_is_served_inline_not_as_a_download(
    client: AsyncClient, seeded: dict
) -> None:
    """Regression test: this endpoint is what the in-app <audio> player's
    src actually points at (frontend/src/api/conversations.ts's
    mediaContentUrl). `Content-Disposition: attachment` (Starlette's
    `FileResponse(..., filename=...)` default) told browsers this was a
    download rather than playable media, which made HTML5 audio
    duration/seeking unreliable — found by manually testing the player
    and seeing a real recording's duration render as 0:00/0:00 despite
    playback otherwise working. Must stay `inline` (with a filename
    still offered, for a user's own "Save audio as...")."""
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    files = {"file": ("session.wav", make_wav_bytes(duration_s=0.3), "audio/wav")}
    upload_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    media = upload_response.json()

    content_response = await client.get(
        f"/api/v1/conversations/{conv['id']}/media/{media['id']}/content", headers=headers
    )
    assert content_response.status_code == 200
    disposition = content_response.headers.get("content-disposition", "")
    assert disposition.startswith("inline"), disposition
    assert "session.wav" in disposition


async def test_conversation_duration_is_synced_from_uploaded_source_audio(
    client: AsyncClient, seeded: dict
) -> None:
    """Regression test: `Conversation.duration_ms` was declared since
    Phase 2 but nothing ever set it — a real, fully "ready" conversation
    with a known-duration source recording still showed "—" everywhere
    (Conversations list, Overview tab), found during manual testing.
    Upload now syncs it from the ingested source audio's own real
    (wave-header-derived) duration."""
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    assert conv["duration_ms"] is None

    data = make_wav_bytes(duration_s=0.3, sample_rate=8000)
    files = {"file": ("session.wav", data, "audio/wav")}
    upload_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    assert upload_response.status_code == 201, upload_response.text
    media = upload_response.json()
    assert media["duration_ms"] == 300

    get_response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["duration_ms"] == 300


async def test_media_access_denied_across_organizations(client: AsyncClient, seeded: dict) -> None:
    alice_headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, alice_headers, seeded["org_a"])
    files = {"file": ("session.wav", make_wav_bytes(), "audio/wav")}
    upload_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=alice_headers
    )
    media = upload_response.json()

    bob_headers = await login(client, "bob", "another very strong pw 456")
    response = await client.get(
        f"/api/v1/conversations/{conv['id']}/media/{media['id']}/content", headers=bob_headers
    )
    assert response.status_code == 404


async def test_deleting_conversation_physically_removes_media(
    client: AsyncClient, seeded: dict
) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    files = {"file": ("session.wav", make_wav_bytes(), "audio/wav")}
    upload_response = await client.post(
        f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers
    )
    media = upload_response.json()

    delete_response = await client.delete(f"/api/v1/conversations/{conv['id']}", headers=headers)
    assert delete_response.status_code == 204

    # Soft-deleted conversation is no longer reachable via normal read.
    get_response = await client.get(f"/api/v1/conversations/{conv['id']}", headers=headers)
    assert get_response.status_code == 404

    # And the underlying media content is genuinely gone, not just hidden.
    content_response = await client.get(
        f"/api/v1/conversations/{conv['id']}/media/{media['id']}/content", headers=headers
    )
    assert content_response.status_code == 404


async def test_participant_marker_note_crud(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    conv_id = conv["id"]

    participant_response = await client.post(
        f"/api/v1/conversations/{conv_id}/participants",
        json={"display_name": "Person A", "participant_type": "patient"},
        headers=headers,
    )
    assert participant_response.status_code == 201
    participant_id = participant_response.json()["id"]
    # Real names are never required — a label like "Person A" is enough.
    assert participant_response.json()["display_name"] == "Person A"

    update_response = await client.patch(
        f"/api/v1/conversations/{conv_id}/participants/{participant_id}",
        json={"display_name": "Person A (updated)"},
        headers=headers,
    )
    assert update_response.status_code == 200

    marker_response = await client.post(
        f"/api/v1/conversations/{conv_id}/markers",
        json={"timestamp_ms": 1500, "label": "Important moment"},
        headers=headers,
    )
    assert marker_response.status_code == 201
    marker_id = marker_response.json()["id"]

    bad_marker_response = await client.post(
        f"/api/v1/conversations/{conv_id}/markers", json={"timestamp_ms": -1}, headers=headers
    )
    assert bad_marker_response.status_code == 422

    note_response = await client.post(
        f"/api/v1/conversations/{conv_id}/notes",
        json={"content": "Patient context noted before recording."},
        headers=headers,
    )
    assert note_response.status_code == 201
    note_id = note_response.json()["id"]

    list_participants = await client.get(
        f"/api/v1/conversations/{conv_id}/participants", headers=headers
    )
    assert len(list_participants.json()) == 1
    list_markers = await client.get(f"/api/v1/conversations/{conv_id}/markers", headers=headers)
    assert len(list_markers.json()) == 1
    list_notes = await client.get(f"/api/v1/conversations/{conv_id}/notes", headers=headers)
    assert len(list_notes.json()) == 1

    await client.delete(
        f"/api/v1/conversations/{conv_id}/participants/{participant_id}", headers=headers
    )
    await client.delete(f"/api/v1/conversations/{conv_id}/markers/{marker_id}", headers=headers)
    await client.delete(f"/api/v1/conversations/{conv_id}/notes/{note_id}", headers=headers)

    assert (
        await client.get(f"/api/v1/conversations/{conv_id}/participants", headers=headers)
    ).json() == []
    assert (
        await client.get(f"/api/v1/conversations/{conv_id}/markers", headers=headers)
    ).json() == []
    assert (
        await client.get(f"/api/v1/conversations/{conv_id}/notes", headers=headers)
    ).json() == []


async def test_mutations_require_csrf_header(client: AsyncClient, seeded: dict) -> None:
    await login(client, "alice", "a very strong password 123")
    response = await client.post(
        "/api/v1/conversations", json={"title": "x", "organization_id": seeded["org_a"]}
    )
    assert response.status_code == 403


async def test_recording_finalize_is_idempotent(client: AsyncClient, seeded: dict) -> None:
    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    data = make_wav_bytes()

    async def finalize():
        return await client.post(
            f"/api/v1/conversations/{conv['id']}/recordings",
            params={"idempotency_key": "rec-abc-123", "original_filename": "recording.wav"},
            content=data,
            headers={**headers, "content-type": "application/octet-stream"},
        )

    first = await finalize()
    assert first.status_code == 201, first.text
    second = await finalize()
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    media_list = await client.get(f"/api/v1/conversations/{conv['id']}/media", headers=headers)
    assert len(media_list.json()) == 1  # no duplicate MediaAsset from the retried finalize


async def test_audit_events_recorded_for_conversation_lifecycle(
    client: AsyncClient, seeded: dict, app_env
) -> None:
    from app.audit.models import AuditEvent
    from sqlalchemy import select

    headers = await login(client, "alice", "a very strong password 123")
    conv = await _create_conversation(client, headers, seeded["org_a"])
    files = {"file": ("session.wav", make_wav_bytes(), "audio/wav")}
    await client.post(f"/api/v1/conversations/{conv['id']}/media", files=files, headers=headers)

    _, sessionmaker = app_env
    async with sessionmaker() as session:
        result = await session.execute(select(AuditEvent.event_type))
        event_types = {row[0] for row in result.all()}

    assert "conversation.created" in event_types
    assert "conversation.uploaded" in event_types
    assert "media.created" in event_types
    # Audit metadata never contains raw content — spot-check the shape.
    async with sessionmaker() as session:
        result = await session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "conversation.created")
        )
        event = result.scalars().first()
        assert event is not None
        assert "title" not in (event.event_metadata or {})
