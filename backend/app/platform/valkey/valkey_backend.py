"""Concrete Valkey implementation of CacheBackend/QueueBackend/CoordinationBackend."""

from __future__ import annotations

from collections.abc import Awaitable
from functools import lru_cache
from typing import Any, cast

from valkey.asyncio import Valkey

from app.platform.config import get_settings


class ValkeyBackend:
    """Single client implementing all three platform.valkey Protocols."""

    def __init__(self, client: Valkey) -> None:
        self._client = client

    # Real bug found by Phase 4 fresh-install testing: valkey-py's async
    # client defaults `socket_timeout` to 5 seconds. `dequeue`'s BLPOP is
    # a server-side blocking call with its own `timeout_seconds` — when
    # that value reaches (or exceeds) the client's socket_timeout, the
    # client's socket-level read can time out a hair before the server's
    # BLPOP actually returns (empty), surfacing as a spurious
    # `valkey.exceptions.TimeoutError` on every idle poll instead of a
    # clean `None`. This was invisible in Phase 3 because both existing
    # workers poll >=2 job types, so `dequeue_next`'s per-queue timeout
    # (`timeout_seconds // len(job_types)`) always landed at 2s — safely
    # under the 5s default. Phase 4's `worker-extraction` polls exactly
    # one job type (EXTRACTION_WORKER_JOB_TYPES), so its per-queue timeout
    # is the full 5s, exactly racing the client default. Fixed at the
    # client level (a generous fixed margin) rather than by constraining
    # future job-type-count combinations to "stay under 5s" by
    # convention.
    _SOCKET_TIMEOUT_SECONDS = 30

    @classmethod
    def from_url(cls, url: str) -> ValkeyBackend:
        return cls(Valkey.from_url(url, socket_timeout=cls._SOCKET_TIMEOUT_SECONDS))

    # -- CacheBackend -----------------------------------------------------
    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    # -- QueueBackend -------------------------------------------------------
    async def enqueue(self, queue_name: str, payload: str) -> None:
        await cast(Awaitable[Any], self._client.rpush(queue_name, payload))

    async def dequeue(self, queue_name: str, *, timeout_seconds: int = 5) -> str | None:
        result = await cast(
            Awaitable[Any], self._client.blpop([queue_name], timeout=timeout_seconds)
        )
        if result is None:
            return None
        _key, value = result
        return value.decode() if isinstance(value, bytes) else value

    async def queue_length(self, queue_name: str) -> int:
        return int(await cast(Awaitable[Any], self._client.llen(queue_name)))

    # -- CoordinationBackend ------------------------------------------------
    async def acquire_lock(self, name: str, *, ttl_seconds: int = 30) -> bool:
        result = await self._client.set(f"lock:{name}", "1", nx=True, ex=ttl_seconds)
        return bool(result)

    async def release_lock(self, name: str) -> None:
        await self._client.delete(f"lock:{name}")

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:  # noqa: BLE001
            return False


@lru_cache
def get_valkey_backend() -> ValkeyBackend:
    """Return the process-wide ValkeyBackend instance."""
    return ValkeyBackend.from_url(get_settings().valkey_url)


async def check_valkey_connectivity() -> bool:
    """Used by the readiness probe."""
    try:
        return await get_valkey_backend().ping()
    except Exception:  # noqa: BLE001
        return False
