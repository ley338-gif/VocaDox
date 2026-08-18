"""Media ingestion: validate, hash, and persist an uploaded/recorded audio
file as an immutable `MediaAsset`.

Consistency model (filesystem + Postgres can't share one ACID transaction):

  1. Spool the incoming bytes to a *temp* file under a controlled temp
     directory (unpredictable name, not the caller's filename), streaming
     rather than buffering fully in memory, while computing SHA-256 and
     enforcing the size cap as bytes arrive.
  2. Validate magic bytes against the supported-format allow-list; reject
     (and delete the temp file) on any mismatch, empty file, or oversize.
  3. Open a DB transaction: INSERT the `MediaAsset` row (flush, not yet
     committed).
  4. Atomically move the temp file into permanent storage
     (`StorageProvider.save_stream`, which prefers `Path.replace` — a
     same-filesystem atomic rename — falling back to a streamed copy).
  5. Commit the DB transaction (caller's responsibility, after this
     function returns, alongside any conversation status transition in the
     same request).

If step 4 fails after step 3's flush, the caller's transaction is rolled
back (so no orphaned `MediaAsset` row is left referencing storage that was
never written) and the temp file has already been cleaned up. If the
process crashes between step 4 and step 5's commit, Postgres rolls the
transaction back automatically on next connection — the storage file may
be an orphan on disk, but no MediaAsset row will ever reference storage
that doesn't exist. Orphaned temp/storage files are addressed by the
temp-cleanup strategy in docs/operations/media-cleanup.md, not by this
function.

Finalize idempotency: callers that need "retry-safe finalize" (the
recording-upload flow) pass an `idempotency_key`; see
`app.media.router` for how a repeated finalize request with the same key
returns the already-created MediaAsset instead of creating a duplicate.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.media.metadata import extract_audio_metadata
from app.media.models import MediaAsset, MediaKind, MediaSourceType
from app.media.validation import UploadValidationError, sniff_audio_format
from app.providers.storage import StorageProvider

_SNIFF_HEAD_BYTES = 64
_STREAM_CHUNK_BYTES = 1024 * 1024  # 1 MiB


class SpooledUpload:
    __slots__ = ("path", "size_bytes", "sha256", "head")

    def __init__(self, path: Path, size_bytes: int, sha256: str, head: bytes) -> None:
        self.path = path
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.head = head


async def spool_upload(
    chunks: AsyncIterator[bytes],
    *,
    temp_dir: str | Path,
    max_size_bytes: int,
) -> SpooledUpload:
    """Stream `chunks` to a temp file, hashing and size-checking as they
    arrive, without ever holding the full payload in memory at once."""
    temp_dir_path = Path(temp_dir)
    temp_dir_path.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 - one-time dir setup

    fd, raw_path = tempfile.mkstemp(dir=temp_dir_path, prefix="upload-", suffix=".tmp")
    path = Path(raw_path)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - best-effort on platforms without POSIX perms
        pass

    hasher = hashlib.sha256()
    total = 0
    head = b""
    try:
        with os.fdopen(fd, "wb") as fh:
            async for chunk in chunks:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_size_bytes:
                    raise UploadValidationError(
                        f"upload exceeds max size of {max_size_bytes} bytes"
                    )
                if len(head) < _SNIFF_HEAD_BYTES:
                    head += chunk[: _SNIFF_HEAD_BYTES - len(head)]
                hasher.update(chunk)
                fh.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)  # noqa: ASYNC240 - error path cleanup, no anyio dependency
        raise

    if total == 0:
        path.unlink(missing_ok=True)  # noqa: ASYNC240 - error path cleanup, no anyio dependency
        raise UploadValidationError("empty upload rejected")

    return SpooledUpload(path=path, size_bytes=total, sha256=hasher.hexdigest(), head=head)


async def bytes_to_chunks(data: bytes) -> AsyncIterator[bytes]:
    for i in range(0, len(data), _STREAM_CHUNK_BYTES):
        yield data[i : i + _STREAM_CHUNK_BYTES]


def _storage_namespace(*, organization_id: uuid.UUID, conversation_id: uuid.UUID, kind: str) -> str:
    subdir = {
        MediaKind.SOURCE_AUDIO.value: "source",
        MediaKind.NORMALIZED_AUDIO.value: "derived",
        MediaKind.ATTACHMENT.value: "attachments",
    }.get(kind, "attachments")
    return f"organizations/{organization_id.hex}/conversations/{conversation_id.hex}/{subdir}"


async def ingest_media(
    session: AsyncSession,
    *,
    spooled: SpooledUpload,
    conversation_id: uuid.UUID,
    organization_id: uuid.UUID,
    kind: MediaKind,
    source_type: MediaSourceType,
    original_filename: str | None,
    created_by_user_id: uuid.UUID,
    storage: StorageProvider,
    derived_from_media_id: uuid.UUID | None = None,
) -> MediaAsset:
    detected = sniff_audio_format(spooled.head)
    if detected is None:
        spooled.path.unlink(missing_ok=True)
        raise UploadValidationError(
            "unsupported or unrecognized audio format (supported: WebM/Opus, WAV, MP3, M4A)"
        )

    metadata = extract_audio_metadata(spooled.path.read_bytes(), container=detected.container)

    media = MediaAsset(
        conversation_id=conversation_id,
        kind=kind.value,
        source_type=source_type.value,
        storage_key="",  # set below, before flush is fine since it's just a string column
        original_filename=original_filename,
        content_type=detected.content_type,
        size_bytes=spooled.size_bytes,
        sha256=spooled.sha256,
        duration_ms=metadata.duration_ms,
        sample_rate=metadata.sample_rate,
        channels=metadata.channels,
        codec=metadata.codec,
        container=detected.container,
        derived_from_media_id=derived_from_media_id,
        created_by_user_id=created_by_user_id,
    )
    session.add(media)
    await session.flush()

    namespace = _storage_namespace(
        organization_id=organization_id, conversation_id=conversation_id, kind=kind.value
    )
    try:
        storage_key = await storage.save_stream(
            spooled.path, suffix=f".{detected.container}", namespace=namespace
        )
    except Exception:
        spooled.path.unlink(missing_ok=True)
        raise
    media.storage_key = storage_key
    await session.flush()
    return media
