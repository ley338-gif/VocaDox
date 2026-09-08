"""Letterhead logo upload (post-GA): PNG/JPEG accepted, oversized/non-image
rejected, round-trips back byte-for-byte, and gated by the same
`template:read`/`template:write` permissions as the rest of the Template
Engine admin surface.
"""

from __future__ import annotations

import base64

from tests.conversations.conftest import login

# A real, valid 1x1 transparent PNG -- python-docx/reportlab actually
# decode the image at export time, so a magic-byte-only stub wouldn't be
# enough for an end-to-end test (see test_export.py), but IS enough here
# since these tests only exercise upload/validation/round-trip, not
# rendering.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def test_upload_letterhead_logo_accepts_png_and_round_trips(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    upload_resp = await client.post(
        "/api/v1/templates/letterhead-logo",
        files={"file": ("logo.png", _TINY_PNG, "image/png")},
        headers=headers,
    )
    assert upload_resp.status_code == 201, upload_resp.text
    asset_key = upload_resp.json()["asset_key"]
    assert asset_key

    get_resp = await client.get(
        f"/api/v1/templates/letterhead-logo/{asset_key}", headers=headers
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.headers["content-type"].startswith("image/png")
    assert get_resp.content == _TINY_PNG


async def test_upload_letterhead_logo_rejects_non_image_content(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/templates/letterhead-logo",
        files={"file": ("not-a-logo.txt", b"this is definitely not an image", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


async def test_upload_letterhead_logo_rejects_oversized_file(client, seeded) -> None:  # noqa: ANN001
    from app.platform.config import get_settings

    headers = await login(client, "carol", "yet another strong pw 789")
    oversized = _TINY_PNG + b"\x00" * (get_settings().max_letterhead_logo_size_bytes + 1)
    resp = await client.post(
        "/api/v1/templates/letterhead-logo",
        files={"file": ("huge.png", oversized, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


async def test_get_unknown_letterhead_logo_asset_key_is_404(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get(
        "/api/v1/templates/letterhead-logo/templates/letterhead/does-not-exist.png",
        headers=headers,
    )
    assert resp.status_code == 404


async def test_letterhead_upload_requires_template_write(client, seeded) -> None:  # noqa: ANN001
    # alice only has template:read (standard User role), not template:write.
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/templates/letterhead-logo",
        files={"file": ("logo.png", _TINY_PNG, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 403
