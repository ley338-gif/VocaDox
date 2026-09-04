"""Service-account API keys, webhook HMAC signing, and SSRF-adjacent URL
validation (Phase 10, spec §54/§55).

API keys: `{key_prefix}.{secret}` — `key_prefix` (8 random hex chars,
stored in cleartext, unique, used only to *look up* the row in O(1))
concatenated with `secret` (a 43-char `secrets.token_urlsafe(32)` value,
never stored — only its Argon2id hash is, via
`app.identity.passwords.hash_password`/`verify_password`, the exact same
utility Phase 1 uses for human passwords; not a second hashing scheme).

Webhook signing follows the well-known Stripe/GitHub pattern: HMAC-SHA256
over `"{timestamp}.{body}"` (the timestamp is folded into the signed
content so a captured payload+signature pair can't be replayed
indefinitely), hex-encoded, in a header shaped `t=<unix_ts>,v1=<hex>`.
`hmac.compare_digest` is used for verification (constant-time).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from urllib.parse import urlsplit

KEY_PREFIX_BYTES = 4  # -> 8 hex chars
SECRET_BYTES = 32  # -> 43 url-safe base64 chars, well above the 12-char password floor

SIGNATURE_HEADER = "X-VocaDox-Signature"
EVENT_HEADER = "X-VocaDox-Event"
DELIVERY_HEADER = "X-VocaDox-Delivery"


def generate_service_account_key() -> tuple[str, str, str]:
    """Returns (key_prefix, secret, full_api_key). Only `full_api_key` is
    ever shown to the admin, exactly once, at creation/rotation time."""
    key_prefix = f"sa_{secrets.token_hex(KEY_PREFIX_BYTES)}"
    secret = secrets.token_urlsafe(SECRET_BYTES)
    return key_prefix, secret, f"{key_prefix}.{secret}"


def parse_api_key(api_key: str) -> tuple[str, str] | None:
    """Splits a Bearer token into (key_prefix, secret). Returns None if the
    token isn't shaped like a VocaDox service-account key at all."""
    if "." not in api_key:
        return None
    key_prefix, _, secret = api_key.partition(".")
    if not key_prefix.startswith("sa_") or not secret:
        return None
    return key_prefix, secret


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def sign_payload(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """Returns the `X-VocaDox-Signature` header value: `t=<ts>,v1=<hex>`."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_content = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Reference verification example for webhook receivers (also used by
    this codebase's own test receiver). Returns False for any malformed
    header rather than raising, since this runs on attacker-controlled
    input by definition."""
    parts = dict(
        item.split("=", 1) for item in signature_header.split(",") if "=" in item
    )
    ts_raw, v1 = parts.get("t"), parts.get("v1")
    if ts_raw is None or v1 is None:
        return False
    try:
        ts = int(ts_raw)
    except ValueError:
        return False
    expected = sign_payload(secret, body, timestamp=ts)
    expected_v1 = expected.split("v1=", 1)[1]
    return hmac.compare_digest(expected_v1, v1)


class UnsafeWebhookURLError(ValueError):
    """Raised when a webhook target URL fails SSRF-adjacent validation."""


# Roadmap-flagged risk (see PHASE_10_VALIDATION_REPORT.md "SSRF
# Mitigation"): webhook targets are admin-supplied and the backend makes
# real outbound requests to them. Default-deny anything that resolves to
# a non-public address so a compromised/careless admin account can't turn
# this feature into an internal port scanner or a cloud metadata-endpoint
# reader (169.254.169.254 et al).
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def validate_webhook_url(url: str) -> None:
    """Raises UnsafeWebhookURLError if `url` is not an acceptable webhook
    target. Resolves the hostname (not just string-matching the literal
    host) so a DNS name that resolves to a private/loopback/link-local
    address is caught too, not only a literal IP in the URL."""
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeWebhookURLError("webhook target URL must use https://")
    host = parsed.hostname
    if not host:
        raise UnsafeWebhookURLError("webhook target URL must have a host")
    if host.lower() in _BLOCKED_HOSTNAMES or host.lower().endswith(".local"):
        raise UnsafeWebhookURLError(f"webhook target host {host!r} is not allowed")

    try:
        ip = ipaddress.ip_address(host)
        _reject_if_unsafe_ip(ip)
        return
    except ValueError:
        pass  # not a literal IP -- resolve it

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise UnsafeWebhookURLError(f"could not resolve webhook target host {host!r}") from exc
    if not infos:
        raise UnsafeWebhookURLError(f"could not resolve webhook target host {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        _reject_if_unsafe_ip(ip)


def _reject_if_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise UnsafeWebhookURLError(f"webhook target resolves to a non-public address ({ip})")
