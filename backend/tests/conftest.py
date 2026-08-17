"""Shared pytest fixtures.

No real Postgres/Valkey required: DB tests below stub connectivity rather
than requiring live infra, matching the CI constraint (no external services
needed at test time).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.core.app_factory import create_app
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
