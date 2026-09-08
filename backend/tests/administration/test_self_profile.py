"""Post-GA: self-service profile editing (`PATCH /auth/me`,
`POST /auth/me/avatar`) -- a user managing their OWN identity fields,
deliberately available to every authenticated user regardless of
`user:manage` (unlike the admin `/admin/users/*` surface), but narrower
in scope than that admin surface: no group/organization/is_active
control, ever, no matter what the request body contains.
"""

from __future__ import annotations

from tests.administration.conftest import login


async def test_get_me_includes_profile_fields(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["first_name"] is None
    assert body["last_name"] is None
    assert body["gender"] is None
    assert body["avatar_asset_key"] is None


async def test_update_own_profile(client, seeded) -> None:  # noqa: ANN001
    """A regular "User"-role account (no user:manage) can edit their own
    profile fields -- this is the whole point of self-service."""
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.patch(
        "/api/v1/auth/me",
        json={
            "first_name": "Alice",
            "last_name": "Example",
            "display_name": "Alice E.",
            "email": "alice.e@example.test",
            "gender": "female",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Example"
    assert body["display_name"] == "Alice E."
    assert body["email"] == "alice.e@example.test"
    assert body["gender"] == "female"

    # Persisted, not just echoed back.
    again = await client.get("/api/v1/auth/me", headers=headers)
    assert again.json()["gender"] == "female"


async def test_update_own_profile_rejects_invalid_gender(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.patch(
        "/api/v1/auth/me", json={"gender": "not-a-real-option"}, headers=headers
    )
    assert resp.status_code == 422


async def test_self_update_cannot_grant_group_org_or_reactivation(client, seeded) -> None:  # noqa: ANN001
    """Extra fields a self-update body might contain (is_active,
    group_ids, organization_ids -- all real admin-only fields) are simply
    not part of SelfUpdateRequest's schema, so they're silently dropped,
    never applied -- proven here by actually checking nothing changed,
    not just trusting the schema."""
    headers = await login(client, "alice", "a very strong password 123")
    before = await client.get("/api/v1/auth/me", headers=headers)
    before_groups = {g["id"] for g in before.json()["groups"]}

    resp = await client.patch(
        "/api/v1/auth/me",
        json={
            "display_name": "Still Alice",
            "is_active": False,
            "group_ids": [],
            "organization_ids": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "Still Alice"

    after = await client.get("/api/v1/auth/me", headers=headers)
    after_groups = {g["id"] for g in after.json()["groups"]}
    assert after_groups == before_groups  # group membership untouched

    # Still able to log in -- is_active was never actually flipped.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "a very strong password 123"},
    )
    assert login_resp.status_code == 200


async def test_upload_and_use_own_avatar_without_user_manage(client, seeded) -> None:  # noqa: ANN001
    """bob has no user:manage (plain "User" role) -- self-service avatar
    upload/assign/view must work anyway; only the admin `/admin/users/*`
    surface is user:manage-gated."""
    headers = await login(client, "bob", "another very strong pw 456")
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
        b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload_resp = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
        headers=headers,
    )
    assert upload_resp.status_code == 201, upload_resp.text
    asset_key = upload_resp.json()["asset_key"]

    assign_resp = await client.patch(
        "/api/v1/auth/me", json={"avatar_asset_key": asset_key}, headers=headers
    )
    assert assign_resp.status_code == 200, assign_resp.text
    assert assign_resp.json()["avatar_asset_key"] == asset_key

    # Serving is also permission-relaxed to "any authenticated user".
    get_resp = await client.get(f"/api/v1/admin/users/avatar/{asset_key}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.content == png_bytes


async def test_patch_me_requires_authentication(client, seeded) -> None:  # noqa: ANN001
    resp = await client.patch("/api/v1/auth/me", json={"display_name": "Nobody"})
    assert resp.status_code == 401
