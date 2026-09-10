# Operations docs

Deployment topologies: `deploy/compose.dev.yml` for local development and
`deploy/compose.prod.yml` for a guarded single-host production deployment.

- [`disaster-recovery.md`](disaster-recovery.md) — backup/restore
  (`app.operations.backup_service`, `app.cli.backup`) and the Retention
  Cleanup Worker (`app.operations.retention_service`, `app.cli.
  retention_cleanup`): what is/isn't backed up, how to restore, real
  RPO/RTO, and an operator setup checklist (Phase 11).
- [`production-deployment.md`](production-deployment.md) — TLS termination,
  required secrets/paths, production validation, startup, and operational
  boundaries for the hardened Compose topology.
- [`offline-model-installation.md`](offline-model-installation.md) — the
  AI-model install/runtime offline story (Phase 3.1): what needs network
  access at install time vs. never at runtime, and the real
  `HF_HUB_OFFLINE=1` enforcement mechanism.
- [`offline-installation.md`](offline-installation.md) — the
  consolidated, whole-application offline-installation guide (Phase 11):
  ties the AI-model story above together with the rest of the stack
  (backend/database/media have no runtime network dependency of their
  own at all).
- [`gpu-runtime.md`](gpu-runtime.md) — enabling NVIDIA GPU access for the
  AI worker containers.
- [`media-cleanup.md`](media-cleanup.md) — manual media storage cleanup
  (superseded for policy-driven deletion by the real Retention Cleanup
  Worker above, Phase 11 — this doc covers the ad hoc/manual case).
- [`processing-troubleshooting.md`](processing-troubleshooting.md) —
  diagnosing stuck/failed processing jobs.
- [`storage-capacity.md`](storage-capacity.md) — monitoring
  media/model storage volume capacity (see also the Admin Portal's
  Storage and Operations > Model Storage pages).
