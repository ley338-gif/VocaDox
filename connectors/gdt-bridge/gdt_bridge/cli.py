"""`python -m gdt_bridge.cli` -- matches the stdlib-argparse CLI style
already used by VocaDox's own `backend/app/cli/*.py` tools.

    python -m gdt_bridge.cli run                  # start watching + polling
    python -m gdt_bridge.cli validate-config       # check config, exit
    python -m gdt_bridge.cli test-connection       # check config + a real API call
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from gdt_bridge.api_client import ApiError, VocaDoxClient
from gdt_bridge.config import load_config
from gdt_bridge.orchestrator import run


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _test_connection(config_path: Path | None) -> int:
    config = load_config(config_path)
    async with VocaDoxClient(config.base_url, config.api_key) as client:
        try:
            await client.list_conversations()
        except ApiError as exc:
            print(f"Connection check FAILED: {exc}")
            return 1
    print(f"Connection check OK against {config.base_url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="gdt-bridge", description="Prototype GDT connector for VocaDox (ADR-0041)."
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to a TOML config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Start watching for inbound files and polling for approvals.")
    subparsers.add_parser("validate-config", help="Load config and exit (no network calls).")
    subparsers.add_parser("test-connection", help="Load config and make one real API call.")

    args = parser.parse_args(argv)
    _configure_logging()

    if args.command == "validate-config":
        config = load_config(args.config)
        print(f"Config OK: base_url={config.base_url} import_dir={config.import_dir}")
        return 0
    if args.command == "test-connection":
        return asyncio.run(_test_connection(args.config))
    if args.command == "run":
        config = load_config(args.config)
        asyncio.run(run(config))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
