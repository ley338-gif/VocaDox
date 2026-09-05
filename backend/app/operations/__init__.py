"""Phase 11: Operations — Worker/GPU/Queue Metrics, Backup, Restore,
Retention Cleanup, Model Storage, Offline Installation, Disaster
Recovery (roadmap §73).

Reuses, rather than duplicates, existing infrastructure wherever
possible:
- Worker/Queue metrics extend `app.administration`'s Phase 7
  Dashboard/Jobs/Workers read-model (same `ProcessingJob` rows).
- GPU metrics reuse Phase 3's `app.providers.device.detect_device_capabilities`
  unchanged.
- Model Storage reuses Phase 7's `app.administration.service.storage_usage`
  helpers, scoped specifically to the models volume.
- Retention Cleanup enforces `app.conversations.models.RetentionPolicy`,
  which has existed since Phase 2 with admin CRUD since Phase 7 but no
  enforcement worker until now.
- Backup/Restore covers PostgreSQL (all relational data) and the media
  storage volume (`app.providers.storage`). Restore is a CLI-only,
  operator-run procedure (see `app.cli.backup`) — deliberately NOT
  exposed as an HTTP endpoint (see this package's `backup_service`
  module docstring for why).
"""

from __future__ import annotations
