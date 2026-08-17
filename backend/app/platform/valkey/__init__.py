"""Valkey-backed queue/cache/coordination abstractions.

Domain code must never import the `valkey` client or a class named
`RedisService` directly — depend on `CacheBackend`, `QueueBackend`, or
`CoordinationBackend` instead. See docs/architecture/adr/0002-valkey-over-redis.md.
"""

from app.platform.valkey.backends import (
    CacheBackend,
    CoordinationBackend,
    QueueBackend,
)
from app.platform.valkey.valkey_backend import (
    ValkeyBackend,
    check_valkey_connectivity,
    get_valkey_backend,
)

__all__ = [
    "CacheBackend",
    "QueueBackend",
    "CoordinationBackend",
    "ValkeyBackend",
    "get_valkey_backend",
    "check_valkey_connectivity",
]
