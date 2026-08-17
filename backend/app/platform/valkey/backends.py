"""Protocol interfaces for the Valkey-backed platform abstractions.

Kept as `Protocol`s (structural typing) rather than ABCs so tests can supply
lightweight fakes without inheriting from anything.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Simple key/value cache with optional TTL."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...


@runtime_checkable
class QueueBackend(Protocol):
    """FIFO job queue. Phase 0 does not run workers against this yet."""

    async def enqueue(self, queue_name: str, payload: str) -> None: ...

    async def dequeue(self, queue_name: str, *, timeout_seconds: int = 5) -> str | None: ...

    async def queue_length(self, queue_name: str) -> int: ...


@runtime_checkable
class CoordinationBackend(Protocol):
    """Distributed locks / coordination primitives."""

    async def acquire_lock(self, name: str, *, ttl_seconds: int = 30) -> bool: ...

    async def release_lock(self, name: str) -> None: ...
