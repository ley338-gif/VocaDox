# VocaDox

**On-premise, evidence-based conversation documentation.**

> **Status: Phase 0 — Architecture & Foundation scaffold.** No domain
> features (authentication, conversations, transcription, ...) are
> implemented yet. This repository currently contains project scaffolding,
> architecture decisions, and compliance tooling only. See
> [`PHASE_0_VALIDATION_REPORT.md`](PHASE_0_VALIDATION_REPORT.md) for the
> full validation report and GO/NO-GO recommendation before Phase 1 begins.

## What VocaDox is

VocaDox turns recorded conversations into structured, auditable
documentation where every generated statement traces back to what was
actually said (or otherwise recorded) — never silently invented. See
[`docs/architecture/domain-model.md`](docs/architecture/domain-model.md)
for the Source → Facts → Document provenance model that makes this
possible, and `VocaDox - Userinterface.png` / `VocaDox - Architektur.png` /
`VocaDox - Stylesystem.png` (repo root) for the original design references.

## Architecture summary

- **Backend**: FastAPI + SQLAlchemy 2.0 (async, `asyncpg` driver) +
  Alembic, organized as one domain package per bounded context under
  `backend/app/` (see [ADR-0001](docs/architecture/adr/0001-monorepo-domain-backend-layout.md)).
  Cross-cutting concerns (config, logging, DB, Valkey, health) live in
  `backend/app/platform/`; external-engine abstractions (speech-to-text,
  diarization, LLM, storage) live in `backend/app/providers/`.
- **Frontend**: React + Vite + TypeScript, React Router, TanStack Query,
  plain CSS with design tokens as CSS custom properties (no Tailwind, no
  Storybook — see [ADR-0006](docs/architecture/adr/0006-no-storybook-design-system.md)).
  Visit `/design-system` for the living style guide.
- **Datastore**: PostgreSQL (sole system of record). **Queue/cache/coordination**:
  Valkey, accessed only through the `CacheBackend`/`QueueBackend`/`CoordinationBackend`
  abstractions (see [ADR-0002](docs/architecture/adr/0002-valkey-over-redis.md)).
  **Media storage**: local filesystem in Phase 0, via `LocalFilesystemStorage`.
- **Compliance**: every dependency, container image, and (eventually) AI
  model is tracked in `compliance/*.yml` against `compliance/license-policy.yml`,
  enforced by `compliance/check_licenses.py` (see below).

Full architecture record: [`docs/architecture/`](docs/architecture/),
including all [ADRs](docs/architecture/adr/) and the
[domain model](docs/architecture/domain-model.md). Security posture:
[`docs/security/threat-model.md`](docs/security/threat-model.md).

## Quickstart

### Prerequisites

- Docker + Docker Compose (recommended path), **or** Python 3.11+ and
  Node.js 20+ for running services directly.

### Run everything with Docker Compose

```sh
cp deploy/.env.example .env
docker compose up -d
```

This runs from the repo root (a root `docker-compose.yml` wraps
`deploy/docker-compose.yml` — see that file's header comment) and starts
Postgres, Valkey, the backend (FastAPI on `:8000`), and the frontend dev
server (Vite on `:5173`). Verify:

```sh
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

To build and run the **production** frontend image (static assets served
via nginx, not the Vite dev server):

```sh
docker build --target runtime -t vocadox-frontend-prod ./frontend
```

### Run the backend directly

```sh
cd backend
python -m venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Checks: `ruff check .`, `mypy app`, `pytest -q`.

### Run the frontend directly

```sh
cd frontend
npm install
npm run dev
```

Checks: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.

### Database migrations

```sh
cd backend
alembic upgrade head
```

Phase 0 ships only a no-op baseline migration (no domain tables yet — see
[ADR-0004](docs/architecture/adr/0004-evidence-first-data-model.md)).

### License / compliance check

```sh
python compliance/check_licenses.py
```

Exits non-zero if any dependency, container image, or model is
`blocked` or `unknown` per `compliance/license-policy.yml`.

## Repository layout

```
backend/            FastAPI app, one package per domain under app/
frontend/            React + Vite app, design system under src/design-system/
compliance/           License policy + dependency/container/model inventories
docs/                 Architecture, security, licenses, and other documentation
deploy/               docker-compose.yml + .env.example
.github/workflows/    CI
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch/PR/commit conventions
and the license policy summary. See [`SECURITY.md`](SECURITY.md) for
vulnerability reporting.

## License notices

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`docs/licenses/`](docs/licenses/).
