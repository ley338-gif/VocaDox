"""Real end-to-end tests for Webhooks (Phase 10, spec §55):

- admin CRUD, secret shown once, delivery log listing
- a REAL signed HTTP delivery to a REAL local receiver
  (tests.integrations.conftest.http_receiver -- a genuine
  http.server.ThreadingHTTPServer, not a mocked transport)
- signature verification accepts the genuine signature and rejects a
  tampered payload
- bounded retry with backoff on a failing target, success stops retries
- no conversation/document content in the default payload
- SSRF-adjacent URL validation
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.integrations.security import UnsafeWebhookURLError, validate_webhook_url, verify_signature
from app.integrations.service import attempt_delivery, dispatch_with_retry
from tests.conversations.conftest import login
from tests.integrations.conftest import wait_for_deliveries


async def _create_webhook_via_service(sessionmaker, *, organization_id, target_url, event_types):
    """Bypasses the admin-facing SSRF check deliberately -- SSRF policy is
    tested separately/directly below against `validate_webhook_url`. This
    helper exists only so delivery-mechanism tests can target a real
    loopback receiver, which the *policy* correctly refuses via the admin
    API (also proven below)."""
    from app.integrations.models import Webhook
    from app.integrations.security import generate_webhook_secret

    async with sessionmaker() as session:
        webhook = Webhook(
            organization_id=uuid.UUID(organization_id),
            name="test-webhook",
            target_url=target_url,
            secret=generate_webhook_secret(),
            event_types=event_types,
        )
        session.add(webhook)
        await session.commit()
        await session.refresh(webhook)
        return webhook


# -- SSRF-adjacent URL validation ----------------------------------------


def test_validate_webhook_url_rejects_http_scheme():
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("http://example.com/hook")


def test_validate_webhook_url_rejects_loopback_literal():
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("https://127.0.0.1/hook")


def test_validate_webhook_url_rejects_localhost_hostname():
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("https://localhost/hook")


def test_validate_webhook_url_rejects_link_local_metadata_address():
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("https://169.254.169.254/latest/meta-data/")


def test_validate_webhook_url_rejects_private_range_literal():
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("https://10.0.0.5/hook")


def test_validate_webhook_url_accepts_public_literal_ip():
    # A real, public, non-reserved IPv4 literal -- exercised without a DNS
    # lookup so this test has no network dependency.
    validate_webhook_url("https://93.184.216.34/hook")


def test_validate_webhook_url_dns_resolution_is_checked(monkeypatch):
    """A hostname that *resolves* to a private address must be rejected
    too, not just a literal private IP in the URL -- proven here by
    stubbing DNS resolution rather than depending on real DNS being
    reachable in CI."""
    import socket

    def fake_getaddrinfo(host, port):  # noqa: ARG001
        return [(socket.AF_INET, None, None, None, ("192.168.1.50", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeWebhookURLError):
        validate_webhook_url("https://internal.example.test/hook")


# -- Admin CRUD + policy enforcement via the real HTTP API -----------------


async def test_admin_create_webhook_rejects_unsafe_target(client, seeded):
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={
            "name": "unsafe",
            "organization_id": seeded["org_a"],
            "target_url": "https://localhost/hook",
            "event_types": ["conversation.created"],
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_admin_create_webhook_secret_shown_once(client, seeded):
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={
            "name": "safe",
            "organization_id": seeded["org_a"],
            "target_url": "https://93.184.216.34/hook",
            "event_types": ["conversation.created"],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "secret" in body and len(body["secret"]) > 20

    listed = await client.get("/api/v1/admin/webhooks", headers=headers)
    assert listed.status_code == 200
    for row in listed.json():
        assert "secret" not in row


async def test_admin_create_webhook_rejects_unknown_event_type(client, seeded):
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/webhooks",
        json={
            "name": "bad-event",
            "organization_id": seeded["org_a"],
            "target_url": "https://93.184.216.34/hook",
            "event_types": ["not.a.real.event"],
        },
        headers=headers,
    )
    assert resp.status_code == 422


# -- Real signed delivery ---------------------------------------------------


async def test_real_signed_delivery_to_local_receiver_and_signature_verification(
    db_sessionmaker, http_receiver
):
    http_receiver.response_status = 200
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=str(uuid.uuid4()),
        target_url=target_url,
        event_types=["conversation.created"],
    )

    async with db_sessionmaker() as session:
        delivery = await attempt_delivery(
            session,
            webhook,
            event_type="conversation.created",
            payload={"event_type": "conversation.created", "conversation_id": "abc123"},
            attempt_number=1,
        )

    assert delivery.status == "success"
    assert delivery.response_status_code == 200
    assert len(http_receiver.received) == 1

    received = http_receiver.received[0]
    signature_header = received["headers"]["X-VocaDox-Signature"]
    body = received["body"]

    # The genuine signature, computed by the exact same secret, verifies.
    assert verify_signature(webhook.secret, body, signature_header) is True
    # A tampered payload does NOT verify against the same signature --
    # this is the "invalid/tampered signature is rejected" merge-gate
    # check, using the reference verification helper a real receiver
    # would call.
    tampered = body.replace(b"abc123", b"tampered")
    assert tampered != body
    assert verify_signature(webhook.secret, tampered, signature_header) is False
    # A signature signed with the WRONG secret also does not verify.
    assert verify_signature("wrong-secret-entirely", body, signature_header) is False

    assert received["headers"]["X-VocaDox-Event"] == "conversation.created"
    payload_sent = json.loads(body)
    assert payload_sent["conversation_id"] == "abc123"


async def test_retry_with_backoff_is_bounded_and_records_every_attempt(
    db_sessionmaker, http_receiver
):
    http_receiver.response_status = 500  # every attempt fails
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=str(uuid.uuid4()),
        target_url=target_url,
        event_types=["conversation.created"],
    )

    await dispatch_with_retry(
        webhook.id,
        "conversation.created",
        {"event_type": "conversation.created"},
        backoff_schedule=(0.0, 0.0),  # 3 total attempts, no real wait -- fast test
    )

    assert len(http_receiver.received) == 3  # bounded: not infinite

    from sqlalchemy import select

    from app.integrations.models import WebhookDelivery

    async with db_sessionmaker() as session:
        result = await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook.id)
            .order_by(WebhookDelivery.attempt_number.asc())
        )
        deliveries = list(result.scalars().all())

    assert [d.attempt_number for d in deliveries] == [1, 2, 3]
    assert [d.status for d in deliveries] == ["failed", "failed", "exhausted"]
    assert all(d.response_status_code == 500 for d in deliveries)


async def test_retry_stops_after_first_success(db_sessionmaker, http_receiver):
    http_receiver.response_status = 200
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=str(uuid.uuid4()),
        target_url=target_url,
        event_types=["conversation.created"],
    )

    await dispatch_with_retry(
        webhook.id,
        "conversation.created",
        {"event_type": "conversation.created"},
        backoff_schedule=(0.0, 0.0, 0.0),
    )

    assert len(http_receiver.received) == 1

    from sqlalchemy import select

    from app.integrations.models import WebhookDelivery

    async with db_sessionmaker() as session:
        result = await session.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook.id)
        )
        deliveries = list(result.scalars().all())
    assert len(deliveries) == 1
    assert deliveries[0].status == "success"


async def test_unreachable_target_is_recorded_as_a_failed_delivery(db_sessionmaker):
    # Nothing listens on this port -- a genuine connection failure, not a
    # mocked one.
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=str(uuid.uuid4()),
        target_url="http://127.0.0.1:1/unreachable",
        event_types=["conversation.created"],
    )
    async with db_sessionmaker() as session:
        delivery = await attempt_delivery(
            session,
            webhook,
            event_type="conversation.created",
            payload={"event_type": "conversation.created"},
            attempt_number=1,
        )
    assert delivery.status == "failed"
    assert delivery.error_message is not None


# -- Real end-to-end: a genuine domain event triggers a genuine delivery ---


async def test_conversation_created_event_triggers_real_webhook_delivery(
    client, seeded, db_sessionmaker, http_receiver
):
    """The full path: real API request creates a conversation -> real
    `record_event("conversation.created", ...)` call (unchanged Phase 2
    code) -> Phase 10's dispatch hook -> real signed HTTP POST to a real
    local receiver. No mocking anywhere on this path."""
    http_receiver.response_status = 200
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=seeded["org_a"],
        target_url=target_url,
        event_types=["conversation.created"],
    )

    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "triggers a webhook", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conversation_id = resp.json()["id"]

    deliveries = await wait_for_deliveries(db_sessionmaker, webhook.id, count=1)
    assert deliveries[-1].status == "success"

    assert len(http_receiver.received) == 1
    payload_sent = json.loads(http_receiver.received[0]["body"])
    assert payload_sent["conversation_id"] == conversation_id
    assert payload_sent["event_type"] == "conversation.created"
    # Spec hard rule: no conversation content in the default payload --
    # only ids/metadata.
    forbidden_keys = {"title", "description", "transcript", "facts", "content"}
    assert forbidden_keys.isdisjoint(payload_sent.keys())
    assert "triggers a webhook" not in json.dumps(payload_sent)


async def test_webhook_not_subscribed_to_event_type_receives_nothing(
    client, seeded, db_sessionmaker, http_receiver
):
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=seeded["org_a"],
        target_url=target_url,
        event_types=["document.approved"],  # NOT conversation.created
    )

    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "should not trigger", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    assert resp.status_code == 201

    import asyncio

    await asyncio.sleep(0.2)  # give any (wrongly) scheduled task a chance to run
    assert len(http_receiver.received) == 0


async def test_webhook_delivery_log_viewer(client, seeded, db_sessionmaker, http_receiver):
    http_receiver.response_status = 200
    target_url = f"http://127.0.0.1:{http_receiver.server_address[1]}/hook"
    webhook = await _create_webhook_via_service(
        db_sessionmaker,
        organization_id=seeded["org_a"],
        target_url=target_url,
        event_types=["conversation.created"],
    )
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "for delivery log", "organization_id": seeded["org_a"]},
        headers=headers,
    )
    assert resp.status_code == 201
    await wait_for_deliveries(db_sessionmaker, webhook.id, count=1)

    admin_headers = await login(client, "carol", "yet another strong pw 789")
    listed = await client.get(
        f"/api/v1/admin/webhooks/{webhook.id}/deliveries", headers=admin_headers
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert body["items"][0]["event_type"] == "conversation.created"
