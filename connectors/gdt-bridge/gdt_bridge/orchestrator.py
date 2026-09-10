"""Ties the inbound folder watcher (a `watchdog` observer running on its
own thread) and the outbound poll loop (an asyncio task) together into
one running process."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from gdt_bridge.api_client import VocaDoxClient
from gdt_bridge.config import BridgeConfig
from gdt_bridge.inbound import process_inbound_file, wait_until_stable
from gdt_bridge.outbound import poll_once
from gdt_bridge.state import StateStore

logger = logging.getLogger("gdt_bridge.orchestrator")


class _InboundHandler(FileSystemEventHandler):
    def __init__(
        self, config: BridgeConfig, client: VocaDoxClient, store: StateStore, loop: asyncio.AbstractEventLoop
    ) -> None:
        self._config = config
        self._client = client
        self._store = store
        self._loop = loop

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not event.src_path.lower().endswith(".gdt"):
            return
        # watchdog callbacks run on its own thread -- hand off to the
        # asyncio loop rather than calling async code directly here.
        asyncio.run_coroutine_threadsafe(self._handle(Path(event.src_path)), self._loop)

    async def _handle(self, path: Path) -> None:
        try:
            if path.resolve().parent != self._config.import_dir.resolve() or not path.is_file():
                raise ValueError("inbound path is not a regular file inside import_dir")
        except (OSError, RuntimeError, ValueError):
            logger.exception("rejected unsafe inbound path %s", path)
            return
        if not await asyncio.to_thread(wait_until_stable, path):
            logger.warning("inbound file disappeared before it stabilized: %s", path)
            return
        try:
            await process_inbound_file(
                path,
                create_conversation=lambda **kw: self._client.create_conversation(**kw),
                create_participant=lambda cid, **kw: self._client.create_patient_participant(
                    cid, **kw
                ),
                record_state=lambda **kw: self._store.record_conversation_created(**kw),
                max_size_bytes=self._config.max_inbound_size_bytes,
            )
            self._config.processed_dir.mkdir(parents=True, exist_ok=True)
            path.rename(self._config.processed_dir / path.name)
        except Exception:
            logger.exception("failed to process inbound file %s", path)
            self._config.failed_dir.mkdir(parents=True, exist_ok=True)
            path.rename(self._config.failed_dir / path.name)


async def run(config: BridgeConfig) -> None:
    for directory in (config.import_dir, config.processed_dir, config.failed_dir, config.export_dir):
        directory.mkdir(parents=True, exist_ok=True)

    store = StateStore(config.state_db_path)
    async with VocaDoxClient(config.base_url, config.api_key) as client:
        loop = asyncio.get_running_loop()
        handler = _InboundHandler(config, client, store, loop)
        observer = Observer()
        observer.schedule(handler, str(config.import_dir), recursive=False)
        observer.start()
        logger.info("watching %s for inbound GDT files", config.import_dir)

        try:
            while True:
                handled = await poll_once(
                    client,
                    store,
                    export_format=config.export_format,
                    export_dir=config.export_dir,
                    poll_interval_seconds=config.poll_interval_seconds,
                    poll_backoff_max_seconds=config.poll_backoff_max_seconds,
                )
                if handled:
                    logger.info("exported %d document(s) this round", handled)
                await asyncio.sleep(config.poll_interval_seconds)
        finally:
            observer.stop()
            observer.join(timeout=5)
