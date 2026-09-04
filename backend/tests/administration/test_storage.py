"""Admin Portal Storage surface: real disk usage figures (`shutil.disk_usage`
+ an actual recursive directory scan), not fabricated."""

from __future__ import annotations

from tests.administration.conftest import login


async def test_storage_requires_system_admin(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/storage", headers=headers)
    assert resp.status_code == 403


async def test_storage_returns_real_disk_figures(client, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/storage", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["media_disk_total_bytes"] > 0
    assert body["media_used_bytes"] >= 0
    assert body["model_volume_disk_total_bytes"] > 0
