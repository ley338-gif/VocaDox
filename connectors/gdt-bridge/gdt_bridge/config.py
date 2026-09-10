"""Connector configuration -- read from environment variables (a
`GDT_BRIDGE_` prefix, matching the shape of VocaDox's own
`VOCADOX_`-prefixed settings) with an optional TOML file overlay via
stdlib `tomllib` (Python 3.11+, no new dependency)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import tomllib


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    # VocaDox connection.
    base_url: str
    api_key: str

    # Local folders. `import_dir` is watched for inbound `.gdt` request
    # files; successfully-processed files move to `processed_dir`,
    # unparseable/rejected ones to `failed_dir`. `export_dir` is where
    # the connector writes the result GDT (+ PDF, for the gdt-pdf
    # variant) once a document is approved.
    import_dir: Path
    processed_dir: Path
    failed_dir: Path
    export_dir: Path
    max_inbound_size_bytes: int = 1024 * 1024

    # Which export format to request once a document is approved.
    export_format: str = "gdt-pdf"  # or "gdt-text"

    # Approval-detection poll loop (see ADR-0041: poll, not webhook, for
    # deployability behind NAT/on-prem).
    poll_interval_seconds: float = 15.0
    poll_backoff_max_seconds: float = 300.0

    # The request-side (PVS -> VocaDox) Satzart number is genuinely
    # unresolved (ADR-0041) -- configurable rather than hardcoded to one
    # guess. `inbound.extract_patient_fields` doesn't actually need to
    # check this against the record's own 8000 field to extract data
    # (the domain field Feldkennungen are the same regardless of
    # Satzart), but it's recorded here so a future stricter validation
    # mode has somewhere to read an expected value from.
    expected_request_satzart: tuple[str, ...] = ("6301", "6302")

    state_db_path: Path = field(default_factory=lambda: Path("gdt_bridge_state.sqlite3"))


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"GDT_BRIDGE_{name}", default)


def load_config(toml_path: Path | None = None) -> BridgeConfig:
    """Environment variables win over TOML file values, which win over
    the dataclass defaults -- the same override order VocaDox's own
    `pydantic-settings`-based config uses."""
    overlay: dict[str, object] = {}
    if toml_path is not None and toml_path.exists():
        with toml_path.open("rb") as fh:
            overlay = tomllib.load(fh)

    def get(name: str, default: object) -> object:
        env_value = _env(name.upper())
        if env_value is not None:
            return env_value
        return overlay.get(name, default)

    base_url = get("base_url", None)
    api_key = get("api_key", None)
    if not base_url or not api_key:
        raise ValueError(
            "base_url and api_key are required (set GDT_BRIDGE_BASE_URL / "
            "GDT_BRIDGE_API_KEY, or provide them in the config TOML file)"
        )
    parsed_base_url = urlsplit(str(base_url))
    local_dev_host = parsed_base_url.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed_base_url.scheme != "https" and not (
        parsed_base_url.scheme == "http" and local_dev_host
    ):
        raise ValueError("base_url must use https:// (http:// is allowed only for localhost)")

    return BridgeConfig(
        base_url=str(base_url),
        api_key=str(api_key),
        import_dir=Path(get("import_dir", "./gdt_import")),
        processed_dir=Path(get("processed_dir", "./gdt_processed")),
        failed_dir=Path(get("failed_dir", "./gdt_failed")),
        export_dir=Path(get("export_dir", "./gdt_export")),
        max_inbound_size_bytes=int(get("max_inbound_size_bytes", 1024 * 1024)),
        export_format=str(get("export_format", "gdt-pdf")),
        poll_interval_seconds=float(get("poll_interval_seconds", 15.0)),
        poll_backoff_max_seconds=float(get("poll_backoff_max_seconds", 300.0)),
    )
