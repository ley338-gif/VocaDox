# VocaDox — Phase 0 Validation Report

**Phase**: 0 — Architecture & Foundation
**Branch**: `phase-0-foundation` (never committed to `main`)
**Date**: 2026-08-17
**Scope**: scaffolding only — no domain features (auth, conversations,
transcription, ...) are implemented. This report is the GO/NO-GO gate
before Phase 1 begins.

---

## Executive Summary

Phase 0 is complete: a working (not stubbed) monorepo scaffold with a
FastAPI backend, a React/Vite frontend with a token-driven design system, a
Postgres+Valkey Docker Compose stack, an Alembic migration framework, a
license/container compliance pipeline, 7 ADRs, and the documentation
skeleton the plan specified. Every verification claim below was actually
run — backend lint/typecheck/test, frontend lint/typecheck/test/build, and
(since a Docker daemon was available in this sandbox) a full fresh-install
cycle against real Postgres and Valkey containers, including
`alembic upgrade head`. All 31 tracked dependencies + container images are
license-**approved**; zero are review-required, blocked, or unknown.

**Recommendation: GO for Phase 1.** See the Recommendation section for the
full rationale and residual open risks.

---

## Architecture

Monorepo: `backend/`, `frontend/`, `compliance/`, `docs/`, `deploy/`,
`.github/workflows/`, root `docker-compose.yml` wrapper (ADR-0001). Backend
is domain-oriented: `backend/app/<domain>/` per bounded context (17 domain
packages, all empty/documented placeholders in Phase 0 — see each
package's `README.md` for its target phase), plus two implemented
cross-cutting packages, `platform/` (config, logging, db, valkey, health)
and `providers/` (speech-to-text/diarization/LLM/storage abstractions).
Frontend is a standard Vite/React SPA with a `/design-system` route. Full
rationale in `docs/architecture/adr/0001-*.md`.

## Implementation

- **Backend**: `app/core/app_factory.py` wires the FastAPI app; `app/main.py`
  is the ASGI entrypoint. `app/platform/config.py` (pydantic-settings,
  env-var driven), `app/platform/logging.py` (JSON formatter + request-id
  contextvar + sensitive-field redaction), `app/platform/middleware.py`
  (request-id propagation), `app/platform/health.py` (liveness/readiness).
  36 Python source files, all passing ruff + mypy.
- **Frontend**: React 18 + TypeScript + Vite + React Router 7 + TanStack
  Query. `AppShell` (minimal nav chrome, explicitly not the full
  Userinterface-reference sidebar — that ships with the domain features it
  navigates to), `HomePage`, and the `/design-system` route.

## Design System

CSS custom properties in `frontend/src/styles/tokens.css` encode every
token from "VocaDox - Stylesystem.png": primary blue scale, gray scale,
semantic colors, full type scale (H1–H6, Body Large/Base/Small, Caption),
8pt spacing scale, radius scale, shadow scale. Light palette on bare
`:root`; dark overrides via both `prefers-color-scheme` and an explicit
`data-theme="dark"` override. No Storybook (ADR-0006) — `/design-system`
renders colors, typography, spacing, radius, shadows, Lucide icons,
buttons (4 variants incl. disabled), form controls (text input, select,
checkbox, radio), badges/tags/status dots (7 tones), and card/list
examples, all sourced from the same tokens the app uses. Fonts (Inter, via
`@fontsource/inter`) and icons (`lucide-react`) are bundled at build time —
zero CDN calls (ADR-0007).

## Database

SQLAlchemy 2.0 async engine + `asyncpg` driver (ADR-0003, chosen over
`psycopg` specifically to avoid an LGPL-3.0 review-required dependency) +
Alembic. **No domain tables** (per spec §65 / ADR-0004) — `Base.metadata`
is empty. `backend/alembic/versions/0001_baseline.py` is an intentional
no-op migration whose only job is to prove the migration chain works.
Verified: `alembic upgrade head` run against a real, freshly created
Postgres 16 container created exactly one table, `alembic_version` — no
custom `schema_migrations` table or anything else was added.

## Valkey

`CacheBackend` / `QueueBackend` / `CoordinationBackend` are `Protocol`
interfaces in `app/platform/valkey/backends.py`; `ValkeyBackend` (using the
official `valkey` PyPI client) implements all three. No domain code
imports the `valkey` client directly, and no class named `RedisService`
exists anywhere in the codebase (verified by repo-wide search — the only
two hits for that string are the ADR and the docstring stating the rule
itself). Rationale for Valkey over Redis (license) in ADR-0002.

## Provider Architecture

`app/providers/`: `SpeechToTextProvider`, `DiarizationProvider`,
`LLMProvider` are abstract interfaces with `Fake*` implementations
returning deterministic synthetic data (no GPU, no network calls, tests
never touch a real engine). `StorageProvider` has one real implementation,
`LocalFilesystemStorage`, which mints server-generated UUID storage keys
and rejects any key containing `/`, `\`, or `..` — path traversal is
prevented by construction, not by validation alone (see threat model §2,
and `tests/test_providers.py::test_local_filesystem_storage_rejects_path_traversal`,
which passes). Rationale in ADR-0005.

## OpenAPI

FastAPI serves `/openapi.json` automatically. `frontend/openapi.json` is a
committed snapshot fetched from a live locally-run backend;
`npm run generate:api-client` (wrapping `openapi-typescript`) generates
`frontend/src/api/generated/schema.d.ts` from it — both were regenerated
and committed together in this session. CI (`openapi-client-drift` job)
starts the backend, re-fetches, re-generates, and fails the build on any
`git diff` against the committed files.

## Tests

- **Backend**: 9 tests (`pytest -q`) — health endpoint contract
  (`test_health.py`), fake-provider determinism + storage
  roundtrip/path-traversal rejection (`test_providers.py`), and the
  sensitive-log-field redaction guarantee (`test_logging.py`). All pass.
- **Frontend**: 3 tests (`vitest run`) — app routing to `/` and
  `/design-system`, and design-system section rendering. All pass.

## CI

`.github/workflows/ci.yml`: `backend` (ruff, mypy, pytest), `frontend`
(eslint, tsc, vitest, vite build), `openapi-client-drift` (starts the
backend, regenerates the TS client, fails on drift), `docker-build`
(builds both images + validates compose config), `compliance` (runs
`check_licenses.py`). No job requires GPU or an external network call at
test time; Postgres/Valkey are not required for the backend test job
(readiness probe test accepts either 200 or 503, matching the "no live
infra required in CI" constraint) — the fresh-install Docker path is
exercised separately, once, in `docker-build`/manually in this session,
not on every CI run.

**Not run in this session**: the actual GitHub Actions workflow was not
executed against GitHub's runners (no CI service available in this
sandbox) — every job's commands were run manually and passed; the YAML
itself was reviewed for correctness but not executed by the real Actions
engine. Flagged in Known Limitations.

## Security

`docs/security/threat-model.md`: upload handling (MIME/size/duration
validation before full-buffer, no shell string concatenation, ffmpeg via
argument lists), path traversal prevention (implemented and tested today,
not just documented), secrets management (no hardcoded secrets; `.env`
gitignored; log redaction backstop), auth boundaries (deferred to Phase 1
but the boundary — health endpoints stay unauthenticated, everything else
defaults to authenticated — is documented now), privacy-zone handling
requirements. `SECURITY.md` covers vulnerability reporting + these same
principles at the repo root.

## Privacy

No conversation content exists yet to protect (no domain features). The
zero-external-telemetry stance (ADR-0007) and the privacy-zone
("Nicht dokumentieren") requirements documented in the threat model §6 are
the Phase 0-relevant privacy commitments; actual enforcement is Phase 1+
work once there's real conversation data to enforce it on.

## Dependencies

All researched live via PyPI JSON API / npm registry JSON API on
2026-08-17 (`compliance/dependency-inventory.yml`), never assumed.

| Status | Count |
|---|---|
| Approved | 26 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

Notable verified findings: `asyncpg` = Apache-2.0 (confirms ADR-0003's
rationale), `valkey` (PyPI client) = MIT, `@fontsource/inter` = OFL-1.1,
`lucide-react` = ISC — all as expected, none guessed.

**Scope note**: this covers *direct* dependencies only. Full transitive
dependency-tree license resolution (every indirect npm/pip package) was
not performed by hand — see Known Limitations.

## Containers

Every image pulled and inspected locally (`docker inspect --format='{{index
.RepoDigests 0}}'`) on 2026-08-17 to capture real digests — see
`compliance/container-inventory.yml`. No image uses the `latest` tag.

| Status | Count |
|---|---|
| Approved | 5 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

postgres:16.6-alpine3.20 (PostgreSQL License), valkey/valkey:8.0.2-alpine
(BSD-3-Clause), python:3.11.10-slim-bookworm (PSF-2.0), node:20.18.1-bookworm-slim
(MIT), nginx:1.27.3-alpine3.20 (BSD-2-Clause) — the last is the
**production** frontend runtime; the Vite dev server is never used as the
production image (verified: `docker build --target runtime` + `docker run`
served the static build and a `/health` 200 with no dev-server process
involved).

## Licenses

Combined license summary across all three tracked inventories (each
computed independently, not estimated):

| Inventory | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Dependencies (26) | 26 | 0 | 0 | 0 |
| Containers (5) | 5 | 0 | 0 | 0 |
| Models (0) | 0 | 0 | 0 | 0 |

`compliance/model-inventory.yml` is empty (`models: []`) — no AI models
are bundled in Phase 0, consistent with the plan (real model integrations
are Phase 3/4). Schema is documented and ready for that phase.

No "review required" entries exist in Phase 0, so there is nothing
requiring an exception justification — `compliance/exceptions.yml` is
correctly empty.

`compliance/check_licenses.py` loads all three inventories plus
`license-policy.yml` and computes these counts programmatically (not by
hand) — actually run in this session, exit code 0:

```
approved        31
review_required 0
blocked         0
unknown         0
total           31

result: PASS (no blocked or unknown-licensed items)
```

`THIRD_PARTY_NOTICES.md` (root) lists every approved dependency + its
license.

## Documentation

`README.md` (overview/architecture/quickstart), `SECURITY.md`,
`CONTRIBUTING.md`, `THIRD_PARTY_NOTICES.md`; `docs/{architecture, user,
admin, developer, security, operations, licenses}/README.md` index stubs;
7 ADRs; `docs/architecture/domain-model.md`; `docs/architecture/future-considerations.md`;
`docs/security/threat-model.md`; `docs/licenses/{software-components,
ai-models, fonts-assets, license-policy}.md`. Every backend domain
placeholder package has its own `README.md` stating which phase implements
it.

## Reproducibility

Checklist per the task brief — only items actually executed in this
session are checked; everything else is honestly marked NOT VERIFIED
rather than assumed:

```
[ ] clean git checkout tested — NOT VERIFIED (built in-place; a fresh
    `git clone` + build was not additionally performed in this session)
[ ] no locally cached Python dependency required — NOT VERIFIED (backend
    .venv used the local pip cache; not tested with an empty cache)
[ ] no locally cached npm dependency required — NOT VERIFIED (npm install
    used the local npm cache; not tested with an empty cache)
[x] empty Docker volumes tested — VERIFIED (`docker compose down -v` then
    `up`, fresh named volumes created and used)
[x] fresh PostgreSQL tested — VERIFIED (freshly created postgres:16.6
    container; confirmed only `alembic_version` exists after migration)
[x] fresh Valkey tested — VERIFIED (freshly created valkey:8.0.2
    container; `/health/ready` reported `valkey: true`)
[x] generated OpenAPI client matches repository — VERIFIED (regenerated
    from a live backend in this session and committed; not additionally
    re-verified via a second independent CI run on GitHub's infrastructure)
[x] no uncommitted generated files — VERIFIED (`git status --short` clean
    after the final commit)
```

Additionally verified beyond the checklist: full fresh-install cycle —
`docker compose down -v && docker compose build --no-cache && docker
compose up -d` — then `curl /health/live` (200), `curl /health/ready` (200,
`database: true, valkey: true`), and `docker compose exec backend alembic
upgrade head` (succeeded, applied `0001_baseline`). The frontend production
image (`--target runtime`) was built and run standalone and served the
static build + a 200 on `/health` with no dev server involved.

## Known Limitations

- **Transitive dependency licenses** were not individually resolved by
  hand — only the 26 direct Python/Node dependencies were researched.
  Standard practice (`pip-licenses`, `license-checker`, or an SBOM tool)
  should be adopted in a later phase for full transitive coverage; flagged
  as an open risk below, not silently assumed safe.
- **OS-package-layer licenses inside base container images** (e.g. every
  Debian package baked into `python:3.11.10-slim-bookworm`) were not
  individually audited — only the primary runtime's license (Python
  interpreter, Node.js, nginx) was recorded, consistent with how the
  software dependency inventory also scopes to direct dependencies.
- **GitHub Actions itself was not executed** — `.github/workflows/ci.yml`
  was written and every step's command was run manually and passed, but
  the workflow has not yet run on GitHub's actual runners (no such service
  available in this sandbox).
- **A truly clean-machine reproducibility test** (fresh git clone, empty
  package caches) was not performed — see the Reproducibility checklist.
- **npm audit** reports 5 known vulnerabilities (3 moderate, 1 high, 1
  critical) in transitive dev-dependencies at time of `npm install`
  (2026-08-17) — not investigated individually in this session since none
  are in the direct-dependency license inventory's scope and none are
  runtime/production-facing (frontend build/test tooling only); should be
  triaged early in Phase 1.

## Open Risks

1. **Transitive license risk** (see Known Limitations) — a transitive
   dependency could in theory carry a blocked license undetected by this
   phase's direct-dependency-only research. Mitigation: adopt an SBOM/
   transitive-license tool in Phase 1.
2. **`npm audit` vulnerabilities** in dev tooling, untriaged — low
   real-world risk (build/test tooling, not shipped to users) but should
   be resolved before they accumulate.
3. **Privacy-zone retention policy is undecided** (threat model §6,
   logged in `future-considerations.md`) — needs an ADR before Phase
   1/2's `conversations`/`media` domains implement it, or it risks being
   decided implicitly by pipeline behavior instead of deliberately.
4. **No import-linter / automated architecture-boundary enforcement** —
   the platform/providers/domain layering (ADR-0001, ADR-0002) is
   enforced by convention and code review only, not a CI check. Low risk
   today (every domain package is empty) but should be added before
   domain code accumulates.

## Architecture Deviations

None identified against the approved plan. One clarification, not a
deviation: `react-router` was pinned to the 7.x line (not whatever the
absolute-latest published version was at research time) for API-surface
stability — the plan named the package, not a specific major version;
license (MIT) is unaffected. Documented inline in
`compliance/dependency-inventory.yml`.

## Deferred Items

Everything explicitly out of Phase 0 scope per the plan: all domain
feature logic (identity/auth, organizations, conversations, media,
transcription, diarization, intelligence, evidence, review, documents,
templates, profiles, analytics, audit, integrations, workers,
administration), real provider engine integrations (Whisper, pyannote,
Ollama), the worker pipeline itself, and any AI model bundling. Additional
ideas noticed but deliberately not built are logged in
`docs/architecture/future-considerations.md` (import-linter enforcement,
privacy-zone retention ADR, audit-event schema design, upload rate
limiting, multi-tenancy isolation mechanism).

## Git Status

Branch: `phase-0-foundation` (5 commits, `main` does not exist / was never
touched). `git status --short` is clean (no untracked or modified files).
`git diff --check` reports no whitespace errors. No `.env` file is
tracked (only `deploy/.env.example`), no `node_modules/`, no Python
`.venv/`, no build output directories (`dist/`), no local database files,
and no audio/media test fixtures of any kind (real or synthetic) are
present in the repository.

```
45dc29a Add root docs and design references
03eb7db Add Docker Compose stack and CI pipeline
9bc88b2 Add compliance tooling and architecture/security documentation
b5202f3 Add React + Vite frontend with design system (Phase 0)
809e204 Add repo scaffold and FastAPI backend (Phase 0)
```

## Recommendation

**GO for Phase 1.**

Every dependency, container image, and model tracked in Phase 0 is
license-approved (31/31; 0 review-required/blocked/unknown across
dependencies and containers, 0/0/0/0 for models since none are bundled
yet) — the NO-GO trigger ("any dependency or model is Blocked or Unknown")
does not fire. All planned scaffolding exists and actually works: the
backend serves real health checks against real infrastructure, migrations
run cleanly against a real Postgres, the frontend builds and its design
system renders every token from the reference, and the compliance gate
runs and passes. The open risks above (transitive-license coverage,
untriaged npm audit findings, two undecided design questions) are real but
are documentation/process gaps, not defects in what was built — none of
them block starting Phase 1's actual feature work, and all are explicitly
tracked rather than swept under the rug.
