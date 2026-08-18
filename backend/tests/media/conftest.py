"""Reuse the identity domain's in-memory-SQLite `db_session` fixture (pytest
fixtures are directory-scoped, so it must be re-exported here to be visible
to tests under tests/media/)."""

from __future__ import annotations

from tests.identity.conftest import db_session  # noqa: F401
