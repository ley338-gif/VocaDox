"""User avatar upload/loading (post-GA admin user-management UI).

A custom avatar is a small, standalone asset (no DB row of its own --
`User.avatar_asset_key` is the only handle), exactly like
`TemplateVersion.letterhead_logo_asset_key`. Reuses that module's PNG/
JPEG format sniffing rather than duplicating it -- the check is entirely
generic (magic bytes only), not template-specific.

Two bundled *preset* avatars (no upload involved at all) are handled
separately, purely as a frontend convention: `User.avatar_asset_key`
values of the form `"preset:<name>"` are resolved by the frontend to a
static image shipped with the build, never touching this module or
`StorageProvider` -- see `frontend/public/avatars/`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from app.media.service import spool_upload
from app.media.validation import UploadValidationError
from app.providers.storage import StorageProvider
from app.templates.letterhead import sniff_image_format, validate_and_normalize_image

_AVATAR_NAMESPACE = "identity/avatars"


async def upload_avatar(
    chunks: AsyncIterator[bytes],
    *,
    temp_dir: str | Path,
    max_size_bytes: int,
    storage: StorageProvider,
) -> str:
    """Returns the opaque `StorageProvider` key -- no DB row is created.
    The caller persists the key directly onto `User.avatar_asset_key`.
    Raises `UploadValidationError` (empty/oversized/unrecognized format),
    same as every other upload path in this codebase."""
    spooled = await spool_upload(chunks, temp_dir=temp_dir, max_size_bytes=max_size_bytes)
    try:
        detected = validate_and_normalize_image(spooled.path, max_size_bytes=max_size_bytes)
    except UploadValidationError:
        spooled.path.unlink(missing_ok=True)
        raise
    try:
        return await storage.save_stream(
            spooled.path, suffix=f".{detected.extension}", namespace=_AVATAR_NAMESPACE
        )
    except Exception:
        spooled.path.unlink(missing_ok=True)
        raise


async def load_avatar(storage: StorageProvider, asset_key: str) -> tuple[bytes, str] | None:
    """Returns `(bytes, content_type)`, or `None` if the asset is missing/
    unreadable -- never raises, so a stale/deleted avatar degrades to "no
    avatar" instead of 500ing a user list."""
    if not asset_key.startswith(f"{_AVATAR_NAMESPACE}/"):
        return None
    try:
        data = await storage.load(asset_key)
    except Exception:
        return None
    detected = sniff_image_format(data[:16])
    if detected is None:
        return None
    return data, detected.content_type
