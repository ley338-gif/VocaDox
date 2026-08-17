"""Media storage provider abstraction, plus the one real Phase 0 implementation.

`LocalFilesystemStorage` is "real" (not a Fake*) because it is plain
filesystem code with no third-party licensed engine behind it. Storage keys
are server-generated UUIDs, never caller-supplied paths, to eliminate path
traversal by construction (see docs/security/threat-model.md).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    @abstractmethod
    async def save(self, data: bytes, *, suffix: str = "") -> str:
        """Persist `data`, returning an opaque storage key (never a caller path)."""
        raise NotImplementedError

    @abstractmethod
    async def load(self, storage_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


class LocalFilesystemStorage(StorageProvider):
    """Stores blobs under `root` keyed by server-generated UUIDs."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        # storage_key is always our own UUID-derived filename; reject anything
        # that isn't, so a corrupted/forged key can never escape `root`.
        if "/" in storage_key or "\\" in storage_key or ".." in storage_key:
            raise ValueError(f"invalid storage key: {storage_key!r}")
        path = (self._root / storage_key).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError(f"storage key escapes storage root: {storage_key!r}")
        return path

    async def save(self, data: bytes, *, suffix: str = "") -> str:
        safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")[:16]
        storage_key = f"{uuid.uuid4().hex}{safe_suffix}"
        self._resolve(storage_key).write_bytes(data)
        return storage_key

    async def load(self, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    async def delete(self, storage_key: str) -> None:
        path = self._resolve(storage_key)
        if path.exists():
            path.unlink()

    async def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()
