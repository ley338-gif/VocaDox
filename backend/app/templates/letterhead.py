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

import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.media.service import spool_upload
from app.media.validation import UploadValidationError
from app.providers.storage import StorageProvider

_LETTERHEAD_NAMESPACE = "templates/letterhead"
MAX_IMAGE_PIXELS = 10_000_000
MAX_IMAGE_DIMENSION = 10_000


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


def validate_and_normalize_image(path: Path, *, max_size_bytes: int) -> DetectedImageFormat:
    """Fully decode and re-encode a bounded PNG/JPEG.

    Magic bytes alone accept truncated files, polyglots and images whose
    compressed dimensions expand into excessive memory. Re-encoding also
    strips EXIF/GPS and other private metadata before the asset is served or
    embedded in an export.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as candidate:
                if candidate.format not in {"PNG", "JPEG"}:
                    raise UploadValidationError(
                        "unsupported or unrecognized image format (supported: PNG, JPEG)"
                    )
                width, height = candidate.size
                if (
                    width < 1
                    or height < 1
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise UploadValidationError("image dimensions exceed the allowed limit")
                candidate.load()
                normalized = ImageOps.exif_transpose(candidate).copy()
                image_format = candidate.format
    except UploadValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError,
            OSError, SyntaxError, ValueError) as exc:
        raise UploadValidationError("malformed or unsafe image rejected") from exc

    if image_format == "JPEG":
        if normalized.mode not in {"RGB", "L"}:
            normalized = normalized.convert("RGB")
        normalized.save(path, format="JPEG", quality=90, optimize=True)
        detected = DetectedImageFormat(extension="jpg", content_type="image/jpeg")
    else:
        if normalized.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
            normalized = normalized.convert("RGBA")
        normalized.save(path, format="PNG", optimize=True)
        detected = DetectedImageFormat(extension="png", content_type="image/png")
    if path.stat().st_size > max_size_bytes:
        raise UploadValidationError("normalized image exceeds the allowed size limit")
    return detected


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
    try:
        detected = validate_and_normalize_image(spooled.path, max_size_bytes=max_size_bytes)
    except UploadValidationError:
        spooled.path.unlink(missing_ok=True)
        raise
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
    if not asset_key.startswith(f"{_LETTERHEAD_NAMESPACE}/"):
        return None
    try:
        data = await storage.load(asset_key)
    except Exception:
        return None
    detected = sniff_image_format(data[:16])
    if detected is None:
        return None
    return data, detected.content_type
