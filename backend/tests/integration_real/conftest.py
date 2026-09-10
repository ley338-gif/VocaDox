"""Fixtures for the real-infrastructure suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from app.core.app_factory import create_app
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Use HTTPS so the production-default Secure session cookie is exercised."""

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="https://testserver") as api_client:
        yield api_client
