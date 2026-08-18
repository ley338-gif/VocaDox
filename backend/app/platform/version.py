"""Single source of truth for the application version string recorded on
every ProcessingRun (spec: "application_version"). Kept separate from
app.core.app_factory (which sets the FastAPI/OpenAPI version) so
non-web code (workers) can import it without pulling in FastAPI.
"""

from __future__ import annotations

APPLICATION_VERSION = "0.0.1"
