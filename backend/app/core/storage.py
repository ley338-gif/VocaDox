"""Storage provider dependency-injection wiring.

Lives in `app/core` (a cross-cutting package per the architecture boundary
rules in tests/test_architecture_boundaries.py), not in any domain
package — domain routers depend on `StorageProvider` (the abstract
interface) via `Depends(get_storage_provider)` and must never import a
concrete implementation like `LocalFilesystemStorage` themselves.
"""

from __future__ import annotations

from app.platform.config import get_settings
from app.providers.storage import LocalFilesystemStorage, StorageProvider


def get_storage_provider() -> StorageProvider:
    settings = get_settings()
    return LocalFilesystemStorage(settings.media_storage_root)
