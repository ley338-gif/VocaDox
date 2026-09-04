"""Shared fixtures for Phase 10 integration tests: reuses the in-memory
SQLite + fake cache app_env/seeded/client/login fixtures from
tests.conversations.conftest (same pattern as every other phase's test
suite), and adds a real local HTTP receiver (a genuine
`http.server.ThreadingHTTPServer` on a background thread, not a mocked
transport) so webhook delivery tests exercise the real outbound HTTP call
end to end.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conversations.conftest import (  # noqa: F401
    app_env,
    client,
    login,
    seeded,
)


class _CapturingHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.received.append(  # type: ignore[attr-defined]
            {"headers": dict(self.headers), "body": body, "path": self.path}
        )
        self.send_response(self.server.response_status)  # type: ignore[attr-defined]
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep test output quiet


class CapturingHTTPServer(ThreadingHTTPServer):
    received: list[dict[str, object]]
    response_status: int


@pytest.fixture
def http_receiver() -> Iterator[CapturingHTTPServer]:
    server = CapturingHTTPServer(("127.0.0.1", 0), _CapturingHandler)
    server.received = []
    server.response_status = 200
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest_asyncio.fixture
async def db_sessionmaker(app_env) -> async_sessionmaker:  # noqa: ANN001, F811
    _app, sessionmaker = app_env
    return sessionmaker


@pytest_asyncio.fixture(autouse=True)
async def _wire_dispatch_sessionmaker(app_env):  # noqa: ANN001, F811
    """Points the webhook dispatch background task's sessionmaker (see
    app.integrations.service._get_dispatch_sessionmaker) at this test's
    in-memory SQLite engine instead of the real process-wide one -- the
    background `asyncio.create_task` webhook delivery spawns has no
    request-scoped session/dependency-override to inherit otherwise."""
    from app.integrations.service import set_dispatch_sessionmaker

    _app, sessionmaker = app_env
    set_dispatch_sessionmaker(sessionmaker)
    yield
    set_dispatch_sessionmaker(None)


async def wait_for_deliveries(
    sessionmaker: async_sessionmaker, webhook_id, *, count: int, timeout: float = 5.0
) -> list:
    from app.integrations.models import WebhookDelivery

    elapsed = 0.0
    step = 0.02
    while elapsed < timeout:
        async with sessionmaker() as session:
            result = await session.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.webhook_id == webhook_id)
                .order_by(WebhookDelivery.attempt_number.asc())
            )
            rows = list(result.scalars().all())
        if len(rows) >= count and rows[-1].status != "pending":
            return rows
        await asyncio.sleep(step)
        elapsed += step
    raise AssertionError(f"timed out waiting for {count} webhook deliveries (got {len(rows)})")
