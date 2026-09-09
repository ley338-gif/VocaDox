"""Outbound half: poll VocaDox for approved documents, then write the
result (PDF+GDT or text-only GDT) into the local export folder.

Poll rather than webhook-push (ADR-0041): this connector is expected to
run on/near a practice PC, typically with no inbound reachability from
VocaDox's backend, so a poll loop is the deployable choice here even
though webhook-push is the pattern documented for VocaDox's other
(still-hypothetical) Fachsystem adapters.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from gdt_bridge.api_client import ExportedFile, VocaDoxClient
from gdt_bridge.gdt_codec import rewrite_field
from gdt_bridge.state import InFlightItem, StateStore

logger = logging.getLogger("gdt_bridge.outbound")

_APPROVED_STATUS = "approved"


def _write_gdt_pdf_bundle(exported: ExportedFile, export_dir: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        pdf_names = [n for n in archive.namelist() if n.endswith(".pdf")]
        gdt_names = [n for n in archive.namelist() if n.endswith(".gdt")]
        if not pdf_names or not gdt_names:
            raise ValueError(f"gdt-pdf export bundle missing expected members: {archive.namelist()}")
        pdf_bytes = archive.read(pdf_names[0])
        gdt_text = archive.read(gdt_names[0]).decode("cp1252")

    pdf_path = export_dir / pdf_names[0]
    gdt_path = export_dir / gdt_names[0]
    pdf_path.write_bytes(pdf_bytes)
    # The backend can only ever emit a bare filename in field 6305 (it
    # has no knowledge of this connector's local filesystem) -- rewrite
    # it here to the real absolute path the PVS will actually read from.
    rewritten = rewrite_field(gdt_text, "6305", str(pdf_path.resolve()))
    gdt_path.write_text(rewritten, encoding="cp1252")


def _write_gdt_text_file(exported: ExportedFile, export_dir: Path) -> None:
    (export_dir / exported.filename).write_bytes(exported.content)


async def check_and_export_one(
    client: VocaDoxClient, store: StateStore, item: InFlightItem, *, export_format: str, export_dir: Path
) -> bool:
    """Returns True if the item was exported (or permanently failed and
    should stop being retried), False if it should be checked again
    later."""
    try:
        status = await client.get_document_status(item.conversation_id)
    except Exception as exc:  # noqa: BLE001 - a transient API failure just gets rescheduled
        logger.warning("status check failed for conversation %s: %s", item.conversation_id, exc)
        return False

    if status != _APPROVED_STATUS:
        return False

    try:
        exported = await client.export_document(item.conversation_id, format=export_format)
        export_dir.mkdir(parents=True, exist_ok=True)
        if export_format == "gdt-pdf":
            _write_gdt_pdf_bundle(exported, export_dir)
        else:
            _write_gdt_text_file(exported, export_dir)
        store.mark_exported(item.id)
        logger.info("exported conversation %s to %s", item.conversation_id, export_dir)
        return True
    except Exception as exc:  # noqa: BLE001 - disclosed to the state store, not swallowed
        logger.exception("export failed for conversation %s", item.conversation_id)
        store.mark_failed(item.id, error=str(exc))
        return True


def next_backoff_seconds(attempt_count: int, *, base: float, cap: float) -> float:
    return min(base * (2**attempt_count), cap)


async def poll_once(
    client: VocaDoxClient,
    store: StateStore,
    *,
    export_format: str,
    export_dir: Path,
    poll_interval_seconds: float,
    poll_backoff_max_seconds: float,
) -> int:
    """Checks every due item once. Returns the number of items that were
    exported (or permanently failed) this round."""
    handled = 0
    for item in store.due_items():
        done = await check_and_export_one(
            client, store, item, export_format=export_format, export_dir=export_dir
        )
        if done:
            handled += 1
        else:
            store.reschedule(
                item.id,
                delay_seconds=next_backoff_seconds(
                    item.attempt_count, base=poll_interval_seconds, cap=poll_backoff_max_seconds
                ),
            )
    return handled
