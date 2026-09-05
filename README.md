# VocaDox

**On-premise, evidence-based conversation documentation.**

> **Status: Phase 12 — Hardening / RC (final phase of the 12-phase
> roadmap, complete).** Local authentication, permission-based RBAC,
> Valkey-backed sessions, CSRF protection, organizations, and audit
> logging (Phase 1); conversations, browser/upload audio capture,
> immutable SHA-256-verified source media, participants/markers/notes,
> and organization-scoped authorization (Phase 2); real local
> speech-to-text (faster-whisper) and speaker diarization
> (pyannote.audio), deterministic transcript alignment, and a reviewable
> transcript UI (Phase 3, hardened in Phase 3.1); a local LLM provider
> (Ollama) with structured, evidence-linked fact extraction (Phase 4);
> Review Wizard, document composition, and an immutable approval workflow
> (Phase 5); versioned Templates and Processing/Model Profiles (Phase 6);
> a full Admin Portal (users/groups/organizations/models/jobs/storage/
> retention/audit) (Phase 7); technical/quality analytics and an
> Evaluation Lab (Phase 8); longitudinal (cross-conversation) comparison
> and follow-up tasks (Phase 9); Service Accounts, scoped API keys, and
> webhooks (Phase 10); operational metrics, backup/restore, and retention
> cleanup (Phase 11); and a final security/privacy/dependency/load/
> failure-recovery hardening audit with a GA readiness determination
> (Phase 12) are all implemented. See
> [`PHASE_12_VALIDATION_REPORT.md`](PHASE_12_VALIDATION_REPORT.md) for the
> final GA (General Availability) recommendation, and the other
> `PHASE_*_VALIDATION_REPORT.md` files at the repo root for each phase's
> own detailed validation record.

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
  **Media storage**: local filesystem, via `LocalFilesystemStorage`
  (namespaced opaque keys as of Phase 2 — see
  [ADR-0013](docs/architecture/adr/0013-media-storage-layout.md)).
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
`deploy/docker-compose.yml` — see that file's header comment) and starts,
in dependency order: Postgres and Valkey, a one-shot `migrate` service
(`alembic upgrade head` — deterministic, runs before anything else that
touches the schema; see
[ADR-0018](docs/architecture/adr/0018-model-installation-strategy.md) and
`docs/admin/fresh-install.md`), the backend (FastAPI on `:8000`),
`worker-speech`/`worker-diarization` (real AI processing, `fake`
providers by default until you install real models — see below), and the
frontend dev server (Vite on `:5173`). Verify:

```sh
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

Then create the first administrator (see "Bootstrapping the first admin
user" below) and, if you want real speech/diarization instead of the
deterministic fake providers, install the AI models (see "Installing AI
models" below) — full walkthrough:
[`docs/admin/fresh-install.md`](docs/admin/fresh-install.md).

**Persistent volumes**: conversation media (`vocadox_backend_data`),
installed AI models (`vocadox_models_data`), Postgres data
(`vocadox_postgres_data`), and Valkey data (`vocadox_valkey_data`) all
live in named Docker volumes. `docker compose down` (without `-v`)
preserves all of them across a restart. **`docker compose down -v`
deletes all of them**, including every locally installed model — this is
real, destructive, and not undoable short of re-installing everything
from scratch.

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

Under Docker Compose, migrations run automatically via the one-shot
`migrate` service — you do not need to run `alembic upgrade head`
yourself for a `docker compose up`. Running the backend directly instead
(without Compose):

```sh
cd backend
alembic upgrade head
```

Phase 0 shipped only a no-op baseline migration (see
[ADR-0004](docs/architecture/adr/0004-evidence-first-data-model.md)); Phase 1
adds identity/RBAC/organizations/audit (`0002_identity_rbac.py`); Phase 2
adds conversations/media/participants/markers/notes/retention
(`0003_conversation_capture.py`); Phase 3 adds processing
jobs/runs/transcripts/diarization (`0004_speech_diarization.py`); Phase
3.1 adds the Transactional Outbox table (`0005_processing_outbox.py`) —
see [ADR-0018](docs/architecture/adr/0018-model-installation-strategy.md)
and `docs/architecture/processing-jobs.md`. All downgrades supported.
Upgrading an existing Phase 1 database: `alembic upgrade head` then
`python -m app.identity.seed` to pick up new RBAC permissions on existing
roles (idempotent — safe to run anytime).

### Bootstrapping the first admin user

```sh
docker compose exec backend python -m app.identity.bootstrap_admin \
  --username admin --display-name "Administrator"
```

(Or, running the backend directly: `python -m app.identity.bootstrap_admin ...`
from `backend/` with `alembic upgrade head` already applied.) See
[`docs/admin/README.md`](docs/admin/README.md) and
[`docs/admin/fresh-install.md`](docs/admin/fresh-install.md) for details.

### Installing AI models (speech-to-text / diarization)

`worker-speech`/`worker-diarization` run with deterministic `fake`
providers by default — no model download happens just from
`docker compose up`. To use real local speech-to-text and speaker
diarization instead:

```sh
docker compose run --rm model-manager install speech-default
docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<your-hf-token> \
  model-manager install diarization-default
```

then set `VOCADOX_SPEECH_PROVIDER=faster_whisper` /
`VOCADOX_DIARIZATION_PROVIDER=pyannote` and restart the two worker
services. Full walkthrough, including what the diarization model
actually needs (three separate Hugging Face repos, not one) and how to
verify no network access happens at runtime once installed:
[`docs/admin/model-installation.md`](docs/admin/model-installation.md),
[`docs/admin/diarization-provider.md`](docs/admin/diarization-provider.md),
[`docs/operations/offline-model-installation.md`](docs/operations/offline-model-installation.md).

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
