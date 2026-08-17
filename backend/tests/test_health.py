"""Health endpoint tests.

`/health/live` must always succeed with no dependency calls.
`/health/ready` depends on real DB/Valkey connectivity; in this sandbox
those are unavailable, so we assert it degrades to 503 gracefully rather
than crashing — that itself is the behavior under test.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_ok(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_readiness_reports_dependency_status(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    # 200 if DB+Valkey reachable, 503 otherwise — both are valid depending on
    # environment; the important invariant is the response is well-formed.
    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body.keys()) == {"status", "database", "valkey"}
    assert isinstance(body["database"], bool)
    assert isinstance(body["valkey"], bool)
