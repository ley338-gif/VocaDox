"""Re-exports the Phase 3 processing fixtures (in-memory SQLite + fake
Valkey + FakeQueueBackend + FakeSpeechProvider/FakeDiarizationProvider/
FakeLLMProvider) so Phase 4 intelligence/evidence/review-issue tests get
the exact same zero-external-infra test environment."""

from __future__ import annotations

from tests.processing.conftest import (  # noqa: F401
    app_env,
    client,
    processing_env,
    seeded,
)
