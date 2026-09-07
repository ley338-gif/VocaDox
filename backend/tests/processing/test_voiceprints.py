"""Post-GA P1-2: voiceprint enrollment and confidence-scored recurring-
speaker suggestions. FakeDiarizationProvider always returns the same two
fixed, deterministic embeddings (SPEAKER_00 / SPEAKER_01) — see
app.providers.diarization — so enrolling from one conversation and
suggesting on a later one is fully deterministic here, no real acoustics
involved.
"""

from __future__ import annotations

from tests.conversations.conftest import login
from tests.processing.conftest import create_conversation_with_source_audio, run_all_jobs


async def _process_and_run(client, headers, conversation_id, sessionmaker, queue, storage):  # noqa: ANN001
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/process/transcript", json={}, headers=headers
    )
    assert resp.status_code == 202, resp.text
    await run_all_jobs(sessionmaker, queue, storage)


async def test_diarization_run_populates_embeddings_with_no_suggestion_yet(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_run(client, headers, conversation_id, sessionmaker, queue, storage)

    resp = await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    speakers = resp.json()
    assert len(speakers) == 2
    for speaker in speakers:
        assert speaker["has_voiceprint"] is True
        # No KnownSpeaker has been enrolled in this organization yet.
        assert speaker["suggested_known_speaker_id"] is None
        assert speaker["suggested_confidence"] is None


async def test_enroll_voiceprint_and_suggest_on_next_conversation(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]

    known = await client.post(
        f"/api/v1/known-speakers?organization_id={org_id}",
        json={"display_name": "Dr. Müller"},
        headers=headers,
    )
    assert known.status_code == 201, known.text
    known_speaker_id = known.json()["id"]
    assert known.json()["has_voiceprint"] is False

    conv1, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    await _process_and_run(client, headers, conv1, sessionmaker, queue, storage)
    speakers1 = (
        await client.get(f"/api/v1/conversations/{conv1}/speakers", headers=headers)
    ).json()
    speaker_00 = next(s for s in speakers1 if s["internal_label"] == "SPEAKER_00")

    enroll_resp = await client.post(
        f"/api/v1/conversations/{conv1}/speakers/{speaker_00['id']}/enroll",
        json={"known_speaker_id": known_speaker_id},
        headers=headers,
    )
    assert enroll_resp.status_code == 200, enroll_resp.text

    known_after = await client.get(
        f"/api/v1/known-speakers?organization_id={org_id}", headers=headers
    )
    known_row = next(k for k in known_after.json() if k["id"] == known_speaker_id)
    assert known_row["has_voiceprint"] is True
    assert known_row["voiceprint_sample_count"] == 1

    conv2, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    await _process_and_run(client, headers, conv2, sessionmaker, queue, storage)
    speakers2 = (
        await client.get(f"/api/v1/conversations/{conv2}/speakers", headers=headers)
    ).json()
    speaker_00_conv2 = next(s for s in speakers2 if s["internal_label"] == "SPEAKER_00")
    speaker_01_conv2 = next(s for s in speakers2 if s["internal_label"] == "SPEAKER_01")

    # Identical embedding -> cosine similarity 1.0, well above threshold.
    assert speaker_00_conv2["suggested_known_speaker_id"] == known_speaker_id
    assert speaker_00_conv2["suggested_confidence"] == 1.0
    # SPEAKER_01's embedding is orthogonal to the enrolled voiceprint -> no
    # suggestion at all, never a low-confidence guess forced through.
    assert speaker_01_conv2["suggested_known_speaker_id"] is None


async def test_accept_suggestion_creates_participant_and_assigns(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]

    known = await client.post(
        f"/api/v1/known-speakers?organization_id={org_id}",
        json={"display_name": "Dr. Müller"},
        headers=headers,
    )
    known_speaker_id = known.json()["id"]

    conv1, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    await _process_and_run(client, headers, conv1, sessionmaker, queue, storage)
    speaker_00_conv1 = next(
        s
        for s in (
            await client.get(f"/api/v1/conversations/{conv1}/speakers", headers=headers)
        ).json()
        if s["internal_label"] == "SPEAKER_00"
    )
    await client.post(
        f"/api/v1/conversations/{conv1}/speakers/{speaker_00_conv1['id']}/enroll",
        json={"known_speaker_id": known_speaker_id},
        headers=headers,
    )

    conv2, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    await _process_and_run(client, headers, conv2, sessionmaker, queue, storage)
    speaker_00_conv2 = next(
        s
        for s in (
            await client.get(f"/api/v1/conversations/{conv2}/speakers", headers=headers)
        ).json()
        if s["internal_label"] == "SPEAKER_00"
    )
    assert speaker_00_conv2["suggested_known_speaker_id"] == known_speaker_id
    assert speaker_00_conv2["participant_id"] is None

    accept_resp = await client.post(
        f"/api/v1/conversations/{conv2}/speakers/{speaker_00_conv2['id']}/accept-suggestion",
        headers=headers,
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accepted = accept_resp.json()
    assert accepted["participant_id"] is not None
    assert accepted["display_label"] == "Dr. Müller"

    participants = (
        await client.get(f"/api/v1/conversations/{conv2}/participants", headers=headers)
    ).json()
    participant = next(p for p in participants if p["id"] == accepted["participant_id"])
    assert participant["known_speaker_id"] == known_speaker_id


async def test_accept_suggestion_without_pending_suggestion_is_rejected(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_run(client, headers, conversation_id, sessionmaker, queue, storage)
    speaker = (
        await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    ).json()[0]

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/speakers/{speaker['id']}/accept-suggestion",
        headers=headers,
    )
    assert resp.status_code == 400


async def test_enroll_rejects_known_speaker_from_different_organization(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")

    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=seeded["org_a"]
    )
    await _process_and_run(client, headers, conversation_id, sessionmaker, queue, storage)

    # Login (a single shared client / cookie jar) as bob only after
    # everything needed as alice is done — logging in again overwrites the
    # session cookie, invalidating alice's `headers`' CSRF token pairing.
    bob_headers = await login(client, "bob", "another very strong pw 456")
    other_org_known = await client.post(
        f"/api/v1/known-speakers?organization_id={seeded['org_b']}",
        json={"display_name": "Someone Else"},
        headers=bob_headers,
    )
    assert other_org_known.status_code == 201, other_org_known.text

    headers = await login(client, "alice", "a very strong password 123")
    speaker = (
        await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    ).json()[0]

    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/speakers/{speaker['id']}/enroll",
        json={"known_speaker_id": other_org_known.json()["id"]},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_enroll_requires_known_speaker_manage_permission(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    """Auditor has speaker:read but neither speaker:assign nor
    known-speaker:manage — mirrors the existing
    test_reassign_segment_speaker_requires_permission pattern."""
    import uuid as _uuid

    from app.identity.service import (
        add_user_to_group,
        assign_role_to_group,
        create_local_user,
        get_or_create_group,
        get_role_by_name,
    )
    from app.organizations.models import OrganizationMembership

    _, sessionmaker, queue, storage = processing_env
    headers = await login(client, "alice", "a very strong password 123")
    org_id = seeded["org_a"]

    known = await client.post(
        f"/api/v1/known-speakers?organization_id={org_id}",
        json={"display_name": "Dr. Müller"},
        headers=headers,
    )
    known_speaker_id = known.json()["id"]

    conversation_id, _ = await create_conversation_with_source_audio(
        client, headers, organization_id=org_id
    )
    await _process_and_run(client, headers, conversation_id, sessionmaker, queue, storage)
    speaker = (
        await client.get(f"/api/v1/conversations/{conversation_id}/speakers", headers=headers)
    ).json()[0]

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
            OrganizationMembership(user_id=dana.id, organization_id=_uuid.UUID(org_id))
        )
        await session.commit()

    dana_headers = await login(client, "dana", "a reasonably strong pw 000")
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/speakers/{speaker['id']}/enroll",
        json={"known_speaker_id": known_speaker_id},
        headers=dana_headers,
    )
    assert resp.status_code == 403
