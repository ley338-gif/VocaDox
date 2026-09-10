"""Admin Portal Users surface: list/view/create/deactivate over the exact
Phase 1 RBAC model — no parallel permission system, gated by the
pre-existing `user:manage` permission."""

from __future__ import annotations

import base64

from tests.administration.conftest import login

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


async def test_list_users_requires_permission(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_create_view_deactivate_user_lifecycle(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    create_resp = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "dave",
            "password": "a brand new strong password",
            "display_name": "Dave",
            "email": "dave@example.test",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    user = create_resp.json()
    assert user["username"] == "dave"
    assert user["is_active"] is True
    assert user["group_ids"] == []

    list_resp = await client.get("/api/v1/admin/users", headers=headers)
    assert list_resp.status_code == 200
    assert any(u["username"] == "dave" for u in list_resp.json())

    get_resp = await client.get(f"/api/v1/admin/users/{user['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "dave@example.test"

    dave_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "dave", "password": "a brand new strong password"},
    )
    assert dave_login.status_code == 200
    dave_session = client.cookies["vocadox_session"]
    headers = await login(client, "carol", "yet another strong pw 789")

    # Deactivation, not deletion — the user row still exists afterward.
    deactivate_resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}", json={"is_active": False}, headers=headers
    )
    assert deactivate_resp.status_code == 200, deactivate_resp.text
    assert deactivate_resp.json()["is_active"] is False

    stale_session = await client.get(
        "/api/v1/auth/me",
        headers={"Cookie": f"vocadox_session={dave_session}"},
    )
    assert stale_session.status_code == 401

    still_listed = await client.get("/api/v1/admin/users", headers=headers)
    assert any(u["username"] == "dave" and u["is_active"] is False for u in still_listed.json())

    # A deactivated user can no longer log in.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "dave", "password": "a brand new strong password"},
    )
    assert login_resp.status_code == 401


async def test_create_user_rejects_duplicate_username(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/users",
        json={"username": "alice", "password": "another strong password", "display_name": "Dup"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_update_user_profile_fields(client, seeded) -> None:  # noqa: ANN001
    """Post-GA: fuller admin editing -- name/gender/avatar, not just
    display_name/email/is_active."""
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "erin",
            "password": "a brand new strong password",
            "display_name": "Erin",
        },
        headers=headers,
    )
    user_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"first_name": "Erin", "last_name": "Example", "gender": "female"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["first_name"] == "Erin"
    assert body["last_name"] == "Example"
    assert body["gender"] == "female"

    # An explicit null clears a previously-set field back to "keine Angabe".
    clear_resp = await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"gender": None}, headers=headers
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["gender"] is None


async def test_update_user_rejects_invalid_gender(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")
    resp = await client.patch(
        f"/api/v1/admin/users/{bob_id}", json={"gender": "not-a-real-option"}, headers=headers
    )
    assert resp.status_code == 422


async def test_assign_user_organizations(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")

    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Radiology", "slug": "radiology"},
        headers=headers,
    )
    org_id = org_resp.json()["id"]

    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")

    resp = await client.patch(
        f"/api/v1/admin/users/{bob_id}", json={"organization_ids": [org_id]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["organization_ids"] == [org_id]

    members_resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
    assert any(m["user_id"] == bob_id for m in members_resp.json())

    # Setting to an empty list actually removes the membership -- a real
    # replace, not an additive-only merge.
    clear_resp = await client.patch(
        f"/api/v1/admin/users/{bob_id}", json={"organization_ids": []}, headers=headers
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["organization_ids"] == []


async def test_upload_and_serve_avatar(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    png_bytes = _TINY_PNG
    upload_resp = await client.post(
        "/api/v1/admin/users/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
        headers=headers,
    )
    assert upload_resp.status_code == 201, upload_resp.text
    asset_key = upload_resp.json()["asset_key"]

    get_resp = await client.get(f"/api/v1/admin/users/avatar/{asset_key}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"] == "image/png"
    assert get_resp.content.startswith(b"\x89PNG\r\n\x1a\n")

    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")
    patch_resp = await client.patch(
        f"/api/v1/admin/users/{bob_id}",
        json={"avatar_asset_key": asset_key},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["avatar_asset_key"] == asset_key


async def test_upload_avatar_rejects_non_image(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/users/avatar",
        files={"file": ("not-an-image.txt", b"hello world", "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_avatar_endpoint_rejects_other_storage_namespaces(
    client, seeded, processing_env  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    _app, _sessionmaker, _queue, storage = processing_env
    media_key = await storage.save(b"secret audio", suffix=".wav", namespace="media/source")
    resp = await client.get(f"/api/v1/admin/users/avatar/{media_key}", headers=headers)
    assert resp.status_code == 404


async def test_admin_set_password_lifecycle(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    create_resp = await client.post(
        "/api/v1/admin/users",
        json={
            "username": "frank",
            "password": "franks original password",
            "display_name": "Frank",
        },
        headers=headers,
    )
    user_id = create_resp.json()["id"]

    # Capture an already-issued Frank session before the administrator
    # changes the credential. The reset must revoke this cookie too, not
    # merely make the old password unusable for future logins.
    frank_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "frank", "password": "franks original password"},
    )
    assert frank_login.status_code == 200
    frank_session = client.cookies["vocadox_session"]
    headers = await login(client, "carol", "yet another strong pw 789")

    reset_resp = await client.post(
        f"/api/v1/admin/users/{user_id}/set-password",
        json={"new_password": "a completely new password"},
        headers=headers,
    )
    assert reset_resp.status_code == 204, reset_resp.text

    stale_session = await client.get(
        "/api/v1/auth/me",
        headers={"Cookie": f"vocadox_session={frank_session}"},
    )
    assert stale_session.status_code == 401

    # The old password no longer works; the new one does.
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "frank", "password": "franks original password"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "frank", "password": "a completely new password"},
    )
    assert new_login.status_code == 200


async def test_admin_set_password_rejects_too_short(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")
    resp = await client.post(
        f"/api/v1/admin/users/{bob_id}/set-password",
        json={"new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_set_password_requires_permission(client, seeded) -> None:  # noqa: ANN001
    carol_headers = await login(client, "carol", "yet another strong pw 789")
    users_resp = await client.get("/api/v1/admin/users", headers=carol_headers)
    bob_id = next(u["id"] for u in users_resp.json() if u["username"] == "bob")

    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        f"/api/v1/admin/users/{bob_id}/set-password",
        json={"new_password": "a completely new password"},
        headers=alice_headers,
    )
    assert resp.status_code == 403
