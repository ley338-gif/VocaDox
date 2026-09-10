from __future__ import annotations

from pathlib import Path

import pytest
from gdt_bridge.config import load_config


def test_remote_base_url_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GDT_BRIDGE_BASE_URL", "http://example.test")
    monkeypatch.setenv("GDT_BRIDGE_API_KEY", "secret")
    with pytest.raises(ValueError, match="must use https"):
        load_config()


def test_localhost_http_remains_available_for_development(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GDT_BRIDGE_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("GDT_BRIDGE_API_KEY", "secret")
    monkeypatch.setenv("GDT_BRIDGE_IMPORT_DIR", str(tmp_path / "in"))
    assert load_config().base_url == "http://127.0.0.1:8000"
