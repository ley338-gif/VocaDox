"""Import every domain package's ORM models so they register on
`Base.metadata`. Imported by `alembic/env.py` (for autogenerate) and by
tests that build schema directly from metadata (e.g. via
`Base.metadata.create_all` against SQLite) — the single place that needs
to know every domain's models module exists.
"""

from __future__ import annotations

from app.audit import models as _audit_models  # noqa: F401
from app.identity import models as _identity_models  # noqa: F401
from app.organizations import models as _organizations_models  # noqa: F401
