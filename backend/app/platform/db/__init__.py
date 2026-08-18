"""Async SQLAlchemy engine/session plumbing.

No domain tables are defined in Phase 0 (see spec §65 / ADR-0004) — this
package only wires the async engine, session factory, and declarative base
that Phase 1+ migrations and models will build on.
"""

from app.platform.db.session import (
    Base,
    get_engine,
    get_session,
    get_sessionmaker,
)

__all__ = ["Base", "get_engine", "get_session", "get_sessionmaker"]
