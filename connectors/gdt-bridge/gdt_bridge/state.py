"""SQLite-backed state for in-flight conversations -- chosen over a
hand-rolled JSON file because two independent loops (the folder-watcher
callback and the outbound poll loop) read and write the same set of
records, and SQLite's file-level locking/atomic writes are far more
robust against a mid-write crash than a read-modify-write JSON file.
`sqlite3` is stdlib -- no new dependency."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS in_flight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_gdt_filename TEXT NOT NULL,
    patient_number TEXT,
    conversation_id TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'awaiting_approval' | 'exported' | 'failed'
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_check_at REAL NOT NULL,
    created_at REAL NOT NULL,
    last_error TEXT
);
"""


@dataclass(slots=True)
class InFlightItem:
    id: int
    source_gdt_filename: str
    patient_number: str | None
    conversation_id: str
    status: str
    attempt_count: int
    next_check_at: float


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record_conversation_created(
        self, *, source_gdt_filename: str, patient_number: str | None, conversation_id: str
    ) -> int:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO in_flight "
                "(source_gdt_filename, patient_number, conversation_id, status, "
                " attempt_count, next_check_at, created_at) "
                "VALUES (?, ?, ?, 'awaiting_approval', 0, ?, ?)",
                (source_gdt_filename, patient_number, conversation_id, now, now),
            )
            return int(cursor.lastrowid)

    def due_items(self) -> list[InFlightItem]:
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, source_gdt_filename, patient_number, conversation_id, "
                "status, attempt_count, next_check_at FROM in_flight "
                "WHERE status = 'awaiting_approval' AND next_check_at <= ?",
                (now,),
            ).fetchall()
        return [InFlightItem(*row) for row in rows]

    def reschedule(self, item_id: int, *, delay_seconds: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE in_flight SET attempt_count = attempt_count + 1, "
                "next_check_at = ? WHERE id = ?",
                (time.time() + delay_seconds, item_id),
            )

    def mark_exported(self, item_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE in_flight SET status = 'exported' WHERE id = ?", (item_id,))

    def mark_failed(self, item_id: int, *, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE in_flight SET status = 'failed', last_error = ? WHERE id = ?",
                (error, item_id),
            )
