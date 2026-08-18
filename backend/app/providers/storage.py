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
    async def save(self, data: bytes, *, suffix: str = "", namespace: str = "") -> str:
        """Persist `data`, returning an opaque storage key (never a caller path).

        `namespace` is an optional set of server-generated path *segments*
        (e.g. ``f"organizations/{org_id}/conversations/{conv_id}/source"``)
        used purely to keep the on-disk layout human-navigable for
        operators. It must never be built from caller/user-supplied
        strings (original filenames, request paths, etc.) — only from
        values the server itself controls (UUIDs, fixed enum literals).
        The returned storage key already encodes the namespace; callers
        must treat it as opaque and pass it back unchanged to `load`/
        `delete`/`exists` — never reconstruct or parse it.
        """
        raise NotImplementedError

    @abstractmethod
    async def save_stream(
        self, source_path: str | Path, *, suffix: str = "", namespace: str = ""
    ) -> str:
        """Persist the file already at `source_path` (e.g. a spooled temp
        upload) without reading it fully into memory, returning an opaque
        storage key. Used for large media uploads."""
        raise NotImplementedError

    @abstractmethod
    async def load(self, storage_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def open_path(self, storage_key: str) -> Path:
        """Return a real filesystem path for streaming reads (e.g. HTTP
        range requests). Callers outside the storage provider must never
        expose this path to clients directly."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


def _sanitize_namespace_segment(segment: str) -> str:
    """Only alphanumerics, `-`, and `_` survive — enough for UUIDs and our
    own fixed enum literals (`source`, `derived`, `attachments`), nothing
    a caller-supplied filename or org name could smuggle a `..` through."""
    cleaned = "".join(c for c in segment if c.isalnum() or c in "-_")
    if not cleaned:
        raise ValueError(f"invalid storage namespace segment: {segment!r}")
    return cleaned


class LocalFilesystemStorage(StorageProvider):
    """Stores blobs under `root`, keyed by server-generated UUIDs, optionally
    nested under a sanitized namespace of server-controlled path segments."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        # storage_key is always our own UUID-derived relative path; reject
        # anything that isn't, so a corrupted/forged key can never escape
        # `root`. `/` is permitted (namespace directories) but `..` and
        # absolute-path forms are not.
        if ".." in storage_key or storage_key.startswith(("/", "\\")) or ":" in storage_key:
            raise ValueError(f"invalid storage key: {storage_key!r}")
        parts = [p for p in storage_key.replace("\\", "/").split("/") if p]
        if not parts:
            raise ValueError(f"invalid storage key: {storage_key!r}")
        path = self._root.joinpath(*parts).resolve()
        root_resolved = self._root.resolve()
        if root_resolved not in path.parents and path != root_resolved:
            raise ValueError(f"storage key escapes storage root: {storage_key!r}")
        return path

    def _build_key(self, *, suffix: str, namespace: str) -> str:
        safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")[:16]
        filename = f"{uuid.uuid4().hex}{safe_suffix}"
        if not namespace:
            return filename
        segments = [_sanitize_namespace_segment(s) for s in namespace.split("/") if s]
        return "/".join([*segments, filename])

    async def save(self, data: bytes, *, suffix: str = "", namespace: str = "") -> str:
        storage_key = self._build_key(suffix=suffix, namespace=namespace)
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return storage_key

    async def save_stream(
        self, source_path: str | Path, *, suffix: str = "", namespace: str = ""
    ) -> str:
        import shutil

        storage_key = self._build_key(suffix=suffix, namespace=namespace)
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Try an atomic rename first (same filesystem — the common case
        # when `source_path` is a spooled temp file under our own temp
        # root); fall back to a streaming copy across filesystems.
        try:
            Path(source_path).replace(path)  # noqa: ASYNC240 - rename is effectively instant
        except OSError:
            # Cross-filesystem fallback only; the common (same-filesystem
            # temp-dir) case above never reaches this blocking copy. No
            # anyio dependency exists in this codebase yet to make this
            # non-blocking — acceptable for Phase 2's scope.
            with open(source_path, "rb") as src, open(path, "wb") as dst:  # noqa: ASYNC230
                shutil.copyfileobj(src, dst)
        return storage_key

    async def load(self, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    async def open_path(self, storage_key: str) -> Path:
        return self._resolve(storage_key)

    async def delete(self, storage_key: str) -> None:
        path = self._resolve(storage_key)
        if path.exists():
            path.unlink()

    async def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()
