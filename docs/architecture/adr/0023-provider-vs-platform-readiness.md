# 0023 — Provider readiness is separate from platform readiness

## Status
Accepted

## Context
`GET /health/ready` (`app/platform/health.py`) is what orchestrators
(Docker healthcheck, Kubernetes readiness probes, load balancers) use to
decide whether to route traffic to this instance. Phase 3 introduces
optional AI models that may not be installed (ADR-0018) — the brief is
explicit: "don't make `/health/ready` fail just because an optional AI
model isn't installed (unless the deployment explicitly requires it)."

## Decision
Two entirely separate endpoints, never merged:

- `GET /health/ready` — unchanged by Phase 3. Still checks only database +
  Valkey connectivity (`check_database_connectivity`,
  `check_valkey_connectivity`). Never imports or calls a speech/
  diarization provider.
- `GET /api/v1/admin/providers/speech` and `GET
  /api/v1/admin/providers/diarization` (`app/administration/router.py`) —
  admin-permission-gated (`provider:read`), report real, honest status
  (`installed`, `device`, `cuda_available`, provider/model/revision) with
  no fallback to a fake "Healthy". A conversation's transcript processing
  will simply fail with `MODEL_UNAVAILABLE` (surfaced to the user/admin
  clearly) if a provider isn't installed — the platform itself stays
  "ready" and continues serving every other feature.

## Consequences
- `docker compose up` with no models installed at all still reports a
  healthy `api` service; only `POST .../process/transcript` (or the admin
  provider-status page) reveals that speech/diarization isn't available
  yet.
- A deployment that *does* want to require a model to be installed before
  considering itself ready can build that check on top of the admin
  provider-status endpoint in its own orchestration layer — VocaDox
  doesn't hardcode that policy into `/health/ready` itself, since not
  every deployment wants it (e.g. an installation still mid-way through
  the model-install step).
- This is a deliberately small, narrow decision — not a general
  "readiness policy framework." If a future phase needs configurable
  strict-mode readiness, that's a new ADR, not a retrofit of this one.
