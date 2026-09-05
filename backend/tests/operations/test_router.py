"""HTTP-level tests for the Phase 11 Operations admin API: RBAC gating,
retention-cleanup dry-run-by-default behavior, and backup failure
handling (using a deliberately-missing pg_dump binary — proves the
failure path records a FAILED BackupRecord and returns a clean error
rather than crashing, without requiring a real Postgres in this
SQLite-backed test suite; the REAL pg_dump/pg_restore round trip against
a real Postgres is exercised separately — see PHASE_11_VALIDATION_REPORT.md).
"""

from __future__ import annotations

from app.platform.config import get_settings

from tests.conversations.conftest import app_env, client, login, seeded  # noqa: F401


async def test_metrics_requires_operations_read(client, seeded):  # noqa: F811
    # No auth at all -> 401.
    resp = await client.get("/api/v1/admin/operations/metrics")
    assert resp.status_code == 401

    # alice is a plain "User" — never granted operations:read.
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/operations/metrics", headers=headers)
    assert resp.status_code == 403

    # carol is System Admin.
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/operations/metrics", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "workers" in body and "gpu" in body and "queue" in body
    assert len(body["workers"]) == 3


async def test_model_storage_endpoint(client, seeded):  # noqa: F811
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/operations/model-storage", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "model_volume_root" in body
    assert isinstance(body["models"], list)


async def test_retention_cleanup_run_defaults_to_dry_run_and_requires_trigger_permission(
    client, seeded  # noqa: F811
):
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post(
        "/api/v1/admin/operations/retention-cleanup/run", json={}, headers=headers
    )
    assert resp.status_code == 403  # alice has no retention-cleanup:trigger

    admin_headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/admin/operations/retention-cleanup/run", json={}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["dry_run"] is True  # the request body omitted dry_run -> safe default
    assert body["status"] == "succeeded"


async def test_retention_cleanup_read_endpoints_require_permission(client, seeded):  # noqa: F811
    admin_headers = await login(client, "carol", "yet another strong pw 789")
    await client.post(
        "/api/v1/admin/operations/retention-cleanup/run", json={}, headers=admin_headers
    )

    # NOTE: `client`'s cookie jar is shared across logins — logging in as
    # alice replaces carol's session cookie in the jar (only the
    # X-CSRF-Token header differs per `headers` dict, not the cookie), so
    # carol must log in again afterward before her session cookie is valid
    # for the next request.
    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get(
        "/api/v1/admin/operations/retention-cleanup/runs", headers=alice_headers
    )
    assert resp.status_code == 403

    admin_headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get(
        "/api/v1/admin/operations/retention-cleanup/runs", headers=admin_headers
    )
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1

    items_resp = await client.get(
        f"/api/v1/admin/operations/retention-cleanup/runs/{runs[0]['id']}/items",
        headers=admin_headers,
    )
    assert items_resp.status_code == 200


async def test_backup_create_requires_backup_trigger_permission(client, seeded):  # noqa: F811
    alice_headers = await login(client, "alice", "a very strong password 123")
    resp = await client.post("/api/v1/admin/operations/backups", headers=alice_headers)
    assert resp.status_code == 403


async def test_backup_create_records_failure_when_pg_dump_missing(
    client, seeded, monkeypatch, tmp_path  # noqa: F811
):
    """No real Postgres is reachable in this SQLite-backed test app, and
    pg_dump may not even be installed on the machine running the test —
    both cases must be handled the same clean way: a FAILED BackupRecord,
    a 500 with a real error detail, never an unhandled crash."""
    settings = get_settings()
    monkeypatch.setattr(settings, "pg_dump_path", str(tmp_path / "does-not-exist-pg_dump"))
    monkeypatch.setattr(settings, "backup_root", str(tmp_path / "backups"))

    admin_headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post("/api/v1/admin/operations/backups", headers=admin_headers)
    assert resp.status_code == 500
    assert "backup failed" in resp.json()["detail"]

    list_resp = await client.get("/api/v1/admin/operations/backups", headers=admin_headers)
    assert list_resp.status_code == 200
    records = list_resp.json()
    assert len(records) == 1
    assert records[0]["status"] == "failed"
