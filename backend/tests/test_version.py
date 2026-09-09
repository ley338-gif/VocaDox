"""Release metadata must stay synchronized across the monorepo."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from app.core.app_factory import create_app
from app.platform.version import APPLICATION_VERSION


def test_release_version_is_consistent() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    backend_metadata = tomllib.loads(
        (repository_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    frontend_metadata = json.loads(
        (repository_root / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    frontend_lock = json.loads(
        (repository_root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    openapi_snapshot = json.loads(
        (repository_root / "frontend" / "openapi.json").read_text(encoding="utf-8")
    )

    versions = {
        APPLICATION_VERSION,
        backend_metadata["project"]["version"],
        frontend_metadata["version"],
        frontend_lock["version"],
        frontend_lock["packages"][""]["version"],
        openapi_snapshot["info"]["version"],
        create_app().version,
    }

    assert versions == {APPLICATION_VERSION}
    core_number = r"(?:0|[1-9]\d*)"
    assert re.fullmatch(rf"{core_number}(?:\.{core_number}){{2}}", APPLICATION_VERSION)
