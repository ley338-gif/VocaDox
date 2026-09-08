"""Letterhead logo upload/validation/loading for a "freeform"
`TemplateVersion` (post-GA — see app.templates.models's docstring).

A logo is a small, standalone asset family (no `MediaAsset` DB row of its
own — a `TemplateVersion.letterhead_logo_asset_key` column is the only
handle, exactly like every other `StorageProvider` caller keyed purely by
its opaque key). Reuses `app.media.service.spool_upload`'s stream/hash/
size-cap step and `app.media.validation.UploadValidationError` (the same
exception every other upload path already raises/handles) — only the
image-format sniffing (PNG/JPEG magic bytes) is new, mirroring
`app.media.validation.sniff_audio_format`'s hand-rolled, ordered-detector
style exactly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.media.service import spool_upload
from app.media.validation import UploadValidationError
from app.providers.storage import StorageProvider

_LETTERHEAD_NAMESPACE = "templates/letterhead"


@dataclass(frozen=True)
class DetectedImageFormat:
    extension: str
    content_type: str


def _is_png(head: bytes) -> bool:
    return head[:8] == b"\x89PNG\r\n\x1a\n"


def _is_jpeg(head: bytes) -> bool:
    return head[:3] == b"\xff\xd8\xff"


_DETECTORS: list[tuple[object, DetectedImageFormat]] = [
    (_is_png, DetectedImageFormat(extension="png", content_type="image/png")),
    (_is_jpeg, DetectedImageFormat(extension="jpg", content_type="image/jpeg")),
]


def sniff_image_format(head: bytes) -> DetectedImageFormat | None:
    """PNG/JPEG only — a letterhead logo, not a general asset store.
    Never trusts the caller's `Content-Type` header alone."""
    for predicate, fmt in _DETECTORS:
        if predicate(head):  # type: ignore[operator]
            return fmt
    return None


async def upload_letterhead_logo(
    chunks: AsyncIterator[bytes],
    *,
    temp_dir: str | Path,
    max_size_bytes: int,
    storage: StorageProvider,
) -> str:
    """Returns the opaque `StorageProvider` key — no DB row is created.
    The caller persists the key directly onto a draft
    `TemplateVersion.letterhead_logo_asset_key`. Raises
    `UploadValidationError` (empty/oversized/unrecognized format), same
    as every other upload path in this codebase."""
    spooled = await spool_upload(chunks, temp_dir=temp_dir, max_size_bytes=max_size_bytes)
    detected = sniff_image_format(spooled.head)
    if detected is None:
        spooled.path.unlink(missing_ok=True)
        raise UploadValidationError(
            "unsupported or unrecognized image format (supported: PNG, JPEG)"
        )
    try:
        return await storage.save_stream(
            spooled.path, suffix=f".{detected.extension}", namespace=_LETTERHEAD_NAMESPACE
        )
    except Exception:
        spooled.path.unlink(missing_ok=True)
        raise


async def load_letterhead_logo(
    storage: StorageProvider, asset_key: str
) -> tuple[bytes, str] | None:
    """Returns `(bytes, content_type)`, or `None` if the asset is missing/
    unreadable — never raises, so a stale or deleted logo degrades an
    export gracefully (no logo in the header) instead of 500ing it.
    Re-sniffs `content_type` from the bytes themselves rather than storing
    it separately, so there's nothing to keep in sync."""
    try:
        data = await storage.load(asset_key)
    except Exception:
        return None
    detected = sniff_image_format(data[:16])
    content_type = detected.content_type if detected is not None else "application/octet-stream"
    return data, content_type
