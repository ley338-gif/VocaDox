# VocaDox — Phase 0 Validation Report

**Phase**: 0 — Architecture & Foundation
**Branch**: `phase-0-foundation` (never committed to `main`)
**Date**: 2026-08-18 (final closeout pass)
**Scope**: scaffolding only — no domain features (auth, conversations,
transcription, ...) are implemented. This report is the GO/NO-GO gate
before Phase 1 begins.

> This is a full rewrite, not an append, reflecting the final Phase 0
> state after two remediation passes: (1) transitive-dependency-tree
> license scanning + npm/pip audit triage, and (2) this closeout pass,
> which resolved the one open judgment call from pass 1 — the frontend
> build/dev image's container vulnerabilities — plus a full final
> re-validation of everything else.

---

## Architecture

Monorepo: `backend/`, `frontend/`, `compliance/`, `docs/`, `deploy/`,
`.github/workflows/`, root `docker-compose.yml` wrapper (ADR-0001).
Backend is domain-oriented: `backend/app/<domain>/` per bounded context
(17 domain packages, all empty/documented placeholders in Phase 0 — see
each package's `README.md` for its target phase), plus two implemented
cross-cutting packages, `platform/` (config, logging, db, valkey, health)
and `providers/` (speech-to-text/diarization/LLM/storage abstractions).
Frontend is a Vite/React SPA with a `/design-system` route. 8 ADRs record
every non-obvious architecture decision, including two made during
remediation (ADR-0003's asyncpg-over-psycopg rationale played out exactly
as predicted; ADR-0008 documents the frontend build image's Alpine-over-
Debian switch).

## Implementation

- **Backend**: `app/core/app_factory.py` wires the FastAPI app;
  `app/main.py` is the ASGI entrypoint. `app/platform/config.py`
  (pydantic-settings, env-var driven), `app/platform/logging.py` (JSON
  formatter + request-id contextvar + sensitive-field redaction),
  `app/platform/middleware.py` (request-id propagation),
  `app/platform/health.py` (liveness/readiness). 39 Python source files
  (36 application + 3 test modules added during remediation), all passing
  ruff + mypy.
- **Frontend**: React 18 + TypeScript + Vite 7 + React Router 7 +
  TanStack Query. `AppShell` (minimal nav chrome, explicitly not the full
  Userinterface-reference sidebar — that ships with the domain features
  it navigates to), `HomePage`, and the `/design-system` route.

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
examples, all sourced from the same tokens the app uses. Fonts (Inter,
via `@fontsource/inter`) and icons (`lucide-react`) are bundled at build
time — zero CDN calls (ADR-0007).

## Database

SQLAlchemy 2.0 async engine + `asyncpg` driver (ADR-0003, chosen over
`psycopg` specifically to avoid an LGPL-3.0 review-required dependency) +
Alembic. **No domain tables** (per spec §65 / ADR-0004) — `Base.metadata`
is empty. `backend/alembic/versions/0001_baseline.py` is an intentional
no-op migration whose only job is to prove the migration chain works.
Verified fresh in this closeout pass: `alembic upgrade head` run against a
freshly created Postgres 16 container (after `docker compose down -v`)
created exactly one table, `alembic_version` — no custom
`schema_migrations` table or anything else was added.

## Valkey

`CacheBackend` / `QueueBackend` / `CoordinationBackend` are `Protocol`
interfaces in `app/platform/valkey/backends.py`; `ValkeyBackend` (using
the official `valkey` PyPI client) implements all three. No domain code
imports the `valkey` client directly, and no class named `RedisService`
exists anywhere in the codebase — this is now a running test
(`backend/tests/test_architecture_boundaries.py`), not just a documented
convention, and it passes. Rationale for Valkey over Redis (license) in
ADR-0002.

## Providers

`app/providers/`: `SpeechToTextProvider`, `DiarizationProvider`,
`LLMProvider` are abstract interfaces with `Fake*` implementations
returning deterministic synthetic data (no GPU, no network calls, tests
never touch a real engine). `StorageProvider` has one real implementation,
`LocalFilesystemStorage`, which mints server-generated UUID storage keys
and rejects any key containing `/`, `\`, or `..` — path traversal is
prevented by construction, not by validation alone (see threat model §2,
and `tests/test_providers.py::test_local_filesystem_storage_rejects_path_traversal`,
which passes). `test_architecture_boundaries.py` additionally verifies
domain packages depend on these interfaces, never a concrete `Fake*`/
`LocalFilesystemStorage` implementation directly. Rationale in ADR-0005.

## OpenAPI

FastAPI serves `/openapi.json` automatically. `frontend/openapi.json` is a
committed snapshot fetched from a live locally-run backend;
`npm run generate:api-client` (wrapping `openapi-typescript`) generates
`frontend/src/api/generated/schema.d.ts` from it. Re-verified fresh in
this closeout pass: started the backend, re-fetched `openapi.json`,
regenerated the TS client, `git diff` showed **no drift**. CI's
`openapi-client-drift` job does the same thing on every run and fails the
build on any difference.

## Tests

- **Backend**: 12 tests (`pytest -q`) — health endpoint contract, fake-
  provider determinism + storage roundtrip/path-traversal rejection,
  sensitive-log-field redaction, and 3 architecture-boundary tests. All
  pass, re-verified in this closeout pass.
- **Frontend**: 3 tests (`vitest run`) — app routing to `/` and
  `/design-system`, and design-system section rendering. All pass on the
  current toolchain (vite 7.3.6 / vitest 4.1.10), re-verified.

## CI

`.github/workflows/ci.yml`: `backend` (ruff, mypy, pytest, **pip-audit**),
`frontend` (eslint, tsc, vitest, vite build, **npm audit**),
`openapi-client-drift`, `docker-build` (builds both shipped images +
validates compose config), `compliance` (regenerates
`dependency-inventory-transitive.yml` from the real resolved trees on
every run, fails on drift against the committed file, then runs the full
license gate), `container-vulnerability-scan` (builds **all three**
images — backend runtime, frontend runtime, frontend build/dev — scans
each with Trivy, fails on any CRITICAL, reports HIGH/MEDIUM/LOW for
visibility).

**GitHub Actions itself was not run on GitHub's infrastructure** — no
remote is configured for this repository (`git remote -v` is empty), and
setting one up / pushing was explicitly out of scope for this pass
(no existing authorized remote to use). Every job's commands were run
manually, on this machine, and passed. This stays a documented
verification limitation, not something represented as tested — see Known
Limitations.

## Security

`docs/security/threat-model.md`: upload handling, path traversal
prevention (implemented and tested, not just documented), secrets
management, auth boundaries (deferred to Phase 1, boundary documented
now), privacy-zone handling requirements. New in the remediation passes:
architecture-boundary enforcement as running tests (see Providers/Valkey
above), `pip-audit`/`npm audit` dependency vulnerability scanning (both
0 findings), and Trivy container vulnerability scanning against all three
build outputs that matter (backend runtime, frontend runtime, frontend
build/dev) — see Security Findings for the full breakdown.

## Privacy

Unchanged from the original scaffold — no conversation content exists yet
to protect (no domain features). Zero-external-telemetry stance
(ADR-0007) and privacy-zone requirements (threat model §6) are the
Phase-0-relevant commitments; enforcement is Phase 1+ work.

## Dependencies

Two tiers, both regenerated from real tooling output in this closeout
pass (not reused from a stale snapshot):

**Direct** (`compliance/dependency-inventory.yml`, 32 packages — one more
than the prior pass's 31: `pydantic-settings`, a real runtime dependency
used in `app/platform/config.py` that had been missing from the inventory
until a version-accuracy sweep in this pass caught the gap):

| Status | Count |
|---|---|
| Approved | 32 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

**Transitive** (`compliance/dependency-inventory-transitive.yml`, 421
resolved packages — freshly regenerated from real `pip-licenses`/
`license-checker` output against the actual installed trees, both
production-only and full-dev, for both ecosystems):

| Status | Count |
|---|---|
| Approved | 419 |
| Review required | 2 |
| Blocked | 0 |
| Unknown | 0 |

The 2 review-required packages are `certifi` and `pathspec` (both
MPL-2.0, both dev-tooling-only transitive deps of `pip-audit`/`mypy`,
never shipped) — **re-verified in this pass as still accurate**: same two
packages, same versions, same license, same disposition as the prior
pass. Explicit sign-off remains in `compliance/exceptions.yml`.

This pass also caught and fixed two other inventory-accuracy gaps beyond
the missing `pydantic-settings` entry: `lucide-react` and `eslint`'s
recorded version numbers had drifted from what's actually installed
(both were showing "latest at research time" figures instead of the
pinned/installed version — license was unaffected in both cases, now
corrected in `dependency-inventory.yml` and `docs/licenses/`).

## Containers

`compliance/container-inventory.yml`, 6 images:

| Status | Count |
|---|---|
| Approved | 6 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

**Node build image resolved in this pass** (was the one open judgment
call from the prior report): switched `node:20.18.1-bookworm-slim` →
`node:22-alpine3.24`, plus an `npm install -g npm@latest && npm cache
clean --force` step. See ADR-0008 for the full comparison across every
current official Node 22 variant (bookworm, trixie, three Alpine point
releases) and Security Findings below for the resulting scan numbers.
Backend (`python:3.11-slim-trixie`) and frontend runtime
(`nginx:1.31.3-alpine3.24`) images are unchanged from the prior
remediation pass.

## Licenses

Four independent inventories, each counted separately (never summed —
`dependency-inventory-transitive.yml` is a superset of
`dependency-inventory.yml`, so adding them would double-count):

| Inventory | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies (32) | 32 | 0 | 0 | 0 |
| Transitive dependencies (421) | 419 | 2 | 0 | 0 |
| Containers (6) | 6 | 0 | 0 | 0 |
| Models (0) | 0 | 0 | 0 | 0 |

`compliance/check_licenses.py`, re-run end-to-end in this pass against
freshly regenerated data — exit code 0:

```
Summary by category (never summed together)
category      approved   review_required   blocked   unknown
direct        32         0                 0         0
transitive    419        2                 0         0
containers    6          0                 0         0
models        0          0                 0         0

result: PASS (no blocked or unknown-licensed items)
```

**0 blocked, 0 unknown across all four inventories.**
`THIRD_PARTY_NOTICES.md` and `docs/licenses/*.md` were regenerated in
this pass to match — see Documentation.

## Security Findings

Every finding below was individually triaged, not filtered or hidden.
Severity buckets follow each tool's own rating.

### Application dependencies (npm audit + pip-audit)

Fully resolved in the prior remediation pass, **re-verified fresh in this
pass**:

| Severity | Found (original) | Current | Disposition |
|---|---|---|---|
| Critical | 1 (`vitest` — Vitest UI arbitrary file read) | 0 | **RESOLVED** |
| High | 1 (`vite` — path traversal + 2 more) | 0 | **RESOLVED** |
| Moderate | 3 (`esbuild`, `vite-node`, `@vitest/mocker`) | 0 | **RESOLVED** |
| Low | 2 (`pytest` tmpdir handling, `setuptools` MANIFEST.in bypass) | 0 | **RESOLVED** |

Re-run in this pass: `npm audit` → **0 vulnerabilities**; `pip-audit` →
**No known vulnerabilities found**.

### Backend runtime image (`vocadox-backend`, `python:3.11-slim-trixie`)

Shipped to customers. Trivy, re-scanned fresh in this pass against a
`--no-cache` rebuild:

| Severity | Count | Disposition |
|---|---|---|
| Critical | 0 | **RESOLVED** (was 23 before remediation) |
| High | 8 | **ACCEPTED** (individually, see table below) |
| Medium | 43 | not gated (rule covers Critical/High only) |
| Low | 56 | not gated |

High findings, each accepted with a specific reason (unchanged from the
prior pass, re-verified still accurate):

| Package(s) | CVE(s) | Disposition reason |
|---|---|---|
| `gzip`, `libacl1`, `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` | CVE-2026-41992, CVE-2026-54369, CVE-2025-69720 | **ACCEPTED** — Debian OS utilities never invoked by our Python ASGI process; no fix published on any current Debian release; `libtinfo6` has reverse-dependencies from other base-image tooling so wasn't force-removed like `perl-base` was. |
| `msgpack` 1.1.2 | GHSA-6v7p-g79w-8964 | **ACCEPTED** — pip's own internally vendored copy (`pip/_vendor/msgpack`), never exposed to application input, not independently patchable without forking pip. |
| `setuptools` 70.3.0 | CVE-2025-47273 | **ACCEPTED** (likely tool artifact) — exhaustive on-disk search confirms only setuptools 84.0.0 (already patched) is actually present; flagged as a probable Trivy scan artifact rather than silently dismissed. |

### Frontend runtime image (`vocadox-frontend`, `runtime` target, `nginx:1.31.3-alpine3.24`)

Shipped to customers. Re-scanned fresh in this pass:

| Severity | Count | Disposition |
|---|---|---|
| Critical | 0 | **RESOLVED** (was 3 before remediation) |
| High | 0 | **RESOLVED** (was 35 before remediation) |
| Medium/Low | 0 | — |

**0 vulnerabilities of any severity.**

### Frontend build/dev image (`node:22-alpine3.24`, `base`/`build`/`dev` stages)

Not shipped to customers (discarded by the multi-stage build /
local-development-only), but actively remediated in this closeout pass
rather than left out of scope:

| Severity | Count (original bookworm image) | Count (final) | Disposition |
|---|---|---|---|
| Critical | 8 | **0** | **RESOLVED** |
| High | 48 | 3 | **ACCEPTED** (see below) |
| Medium | — | 6 | not gated |

Path to 0 Critical (full detail in ADR-0008): evaluated
`node:22-bookworm-slim` (6 Critical, `perl-base`) and
`node:22-trixie-slim` (5 Critical, `perl-base` again — Debian ships perl
with unfixable-anywhere CVEs on every current release). Alpine doesn't
ship perl; `node:22-alpine3.21`/`3.22`/`3.24` all showed 5 Critical
instead, but every one was npm's own vendored `tar`/`brace-expansion`/
`ip-address` bundled inside the image's pre-installed npm. Adding
`npm install -g npm@latest && npm cache clean --force` as the first
Dockerfile step replaced those vendored copies and dropped Critical to 0.

Remaining 3 High, both accepted:

| Package | CVE(s) | Disposition reason |
|---|---|---|
| `brace-expansion` (x2) | CVE-2026-14257, CVE-2026-69152 | **ACCEPTED** — still vendored inside npm's own dependency tree even at `npm@latest`; not independently patchable without forking npm. |
| `ip-address` | CVE-2026-69192 | **ACCEPTED** — same reasoning as above. |

Verified end-to-end after the switch: `npm install`, `lint`, `typecheck`,
`test` all pass inside the new image; the `runtime` target still builds
and serves correctly via nginx (confirmed via response headers — `Server:
nginx/1.31.3`, no Vite dev-server client script present). No application
dependency was changed to make this work.

## Documentation

`README.md`, `SECURITY.md`, `CONTRIBUTING.md`; `THIRD_PARTY_NOTICES.md`
**fully regenerated in this pass** to cover direct dependencies (32),
the transitive tier (421, summarized), containers (6, including the new
node image), fonts/icons, compliance/build tooling as its own explicit
section, and AI models (none) — direct and transitive are now kept
conceptually distinguishable in prose, not just in the YAML.
`docs/licenses/{software-components,license-policy,fonts-assets,ai-models}.md`
likewise updated: `software-components.md` gained a Containers section
and a Compliance/build tooling section; `license-policy.md` documents the
handful of exotic-but-legitimate permissive licenses discovered during
transitive scanning (`MIT-0`, `PSF-2.0`, `BlueOak-1.0.0`, `CC0-1.0`,
`CC-BY-3.0`/`4.0`) and the four-inventory enforcement model;
`fonts-assets.md` had its `lucide-react` version corrected to match what's
actually installed. 8 ADRs (added ADR-0008 in this pass);
`docs/architecture/domain-model.md`; `docs/security/threat-model.md`.
Every backend domain placeholder package has its own `README.md`.

## Reproducibility

Checklist, all items genuinely executed (not estimated):

```
[x] clean git checkout tested — VERIFIED (prior pass: `git clone
    --branch phase-0-foundation` into a scratch directory; not re-run in
    this closeout pass since no dependency-tree-altering change was made
    beyond the node base image, which doesn't affect backend/frontend
    application dependency reproducibility)
[x] no locally cached Python dependency required — VERIFIED (prior pass;
    fresh venv, `--no-cache-dir` install, all tests pass)
[x] no locally cached npm dependency required — VERIFIED (prior pass;
    fresh npm cache, 0 vulnerabilities, all checks pass)
[x] empty Docker volumes tested — VERIFIED (this pass: `docker compose
    down -v` then `up` against the final Dockerfiles; fresh named volumes)
[x] fresh PostgreSQL tested — VERIFIED (this pass: fresh postgres
    container; only `alembic_version` exists after migration)
[x] fresh Valkey tested — VERIFIED (this pass: fresh valkey container;
    `/health/ready` body reports `"valkey": true`)
[x] generated OpenAPI client matches repository — VERIFIED (this pass:
    regenerated from a live backend, `git diff` clean)
[x] no uncommitted generated files — VERIFIED (`git status --short`
    clean after the final commit; compliance scan intermediates
    correctly gitignored, not committed)
```

Additionally re-verified in this pass: full fresh-install Docker cycle
(`down -v` → `build --no-cache` → `up -d`) → `/health/live` 200,
`/health/ready` 200 with `{"status":"ready","database":true,"valkey":true}`,
`alembic upgrade head` succeeded. Frontend production image rebuilt and
smoke-tested standalone: `Server: nginx/1.31.3` header present, zero
Vite-dev-server artifacts in the served HTML — confirmed it is genuinely
the static production build, not the dev server.

## Known Limitations

- **GitHub Actions was not executed on GitHub's infrastructure** — no
  remote is configured for this repository, and setting one up was out
  of scope for this pass (no pre-existing authorized push path). Every
  CI job's commands were run manually and passed; the YAML was reviewed
  for correctness but not executed by the real Actions engine.
- **OS-package-layer license identification** inside base container
  images is still not exhaustively cross-checked for license (only
  vulnerability-scanned) — the primary runtime's license is recorded,
  consistent with how the software dependency inventory scopes to direct
  dependencies plus the now-complete transitive tier.
- **8 High findings remain accepted (not fixed)** on the backend runtime
  image, and **3 High findings remain accepted** on the frontend build/dev
  image — see Security Findings' disposition tables. All have no
  upstream fix currently available, or are vendored-internal dependencies
  of pip/npm themselves, not independently patchable without forking
  those tools.
- **The clean-checkout / no-cache-install reproducibility tests were not
  re-run in this closeout pass** — they were genuinely executed in the
  prior remediation pass and nothing in this pass touched
  backend/frontend application dependencies (only the node *build image*,
  which doesn't affect a local `pip install`/`npm install` reproducibility
  test). Re-verify if a future change touches `pyproject.toml` or
  `package.json` again.

## Open Risks

1. **8 accepted High findings on the backend runtime image** and **3 on
   the frontend build/dev image** — no upstream fix exists for most of
   them on any current release of their respective base distributions;
   revisit whenever the base images are next refreshed or upstream ships
   a backport.
2. **Privacy-zone retention policy still undecided** (unchanged,
   `future-considerations.md`).
3. **No automated architecture-boundary enforcement beyond the three
   targeted tests** in `test_architecture_boundaries.py` — sufficient for
   Phase 0's all-placeholder domains, likely to need strengthening (or an
   `import-linter` adoption) once real domain code accumulates in
   Phase 1+.
4. **GitHub Actions has never actually run** — the workflow is untested
   on real CI infrastructure; the first real push to a configured GitHub
   remote should be watched closely for anything that only manifests in
   that environment (network/proxy differences, GitHub-hosted-runner
   Docker socket behavior, etc.).
5. **`npm install -g npm@latest` in the frontend Dockerfile** pulls
   whatever the current npm major version is at build time — this
   self-heals as npm patches things upstream, but also means a future
   npm major bump happens automatically on every image rebuild without an
   explicit version bump commit. Worth revisiting if that ever causes an
   unexpected break.

## Architecture Deviations

None beyond what's already documented inline: `react-router` pinned to
7.x (API stability, license unaffected); `vite` ended up on 7.3.6 rather
than the originally-planned 5.x line, purely as a consequence of npm audit
remediation; the frontend build/dev base image is Alpine (musl libc)
rather than Debian (glibc) as originally scaffolded, per ADR-0008 — no
functional impact, verified by running the full build/lint/typecheck/test
suite inside the new image.

## Deferred Items

Unchanged from prior reports — all domain feature logic, real provider
engine integrations, the worker pipeline, and AI model bundling remain
Phase 1+ work. No new entries added to `future-considerations.md` in this
pass beyond what's already tracked in Open Risks above.

## Git Status

Branch: `phase-0-foundation`. `git status --short` is clean (no untracked
or modified files) after the final commit. `git diff --check` reports no
whitespace errors (only line-ending-normalization notices, which are not
errors). No `.env` file is tracked (only `deploy/.env.example`), no
`node_modules/`, no Python `.venv/`, no build output directories, and
`compliance/_raw_*`/`_container-scan/` (regenerable scan intermediates)
are gitignored rather than committed. Repo-wide grep swept for
`ConvoInsight` (0 hits), `RedisService` (4 hits, all prose/enforcement-code
stating the prohibition, no actual class), `TODO-LICENSE` (0 hits),
`node:20.18.1-bookworm-slim` (present only in historical "switched from"
narrative text in ADR-0008/container-inventory.yml/this report — the
actual `frontend/Dockerfile` FROM line uses `node:22-alpine3.24`), `latest`
as a container tag (0 hits — every image is pinned by tag + digest), and
unresolved `UNKNOWN` inventory entries (0 — every `UNKNOWN` hit is either
policy-bucket vocabulary or a code default, never an actual unresolved
entry in the YAML data). No secrets, real patient/conversation data, or
media files anywhere in the repository.

## Recommendation

**GO for Phase 1.**

Applying the exact rule specified for this closeout: GO only if ALL of
the following hold — checked against the final, freshly-regenerated state:

| Condition | Result |
|---|---|
| Direct: blocked = 0 & unknown = 0 | ✅ 0 / 0 |
| Transitive: blocked = 0 & unknown = 0 | ✅ 0 / 0 |
| Containers: blocked = 0 & unknown = 0 | ✅ 0 / 0 |
| Models: blocked = 0 & unknown = 0 | ✅ 0 / 0 |
| Shipped runtime images: Critical = 0 | ✅ backend 0, frontend 0 |
| Build/dev image: Critical = 0 (or explicit open decision if unavoidable) | ✅ **achieved 0** — not an unavoidable-exception case |
| Remaining shipped High findings have documented disposition | ✅ 8 (backend) + 3 (frontend build/dev), each individually justified above |
| THIRD_PARTY_NOTICES current | ✅ regenerated this pass |
| docs/licenses current | ✅ regenerated this pass |
| All backend tests pass | ✅ 12/12 |
| All frontend tests pass | ✅ 3/3 |
| OpenAPI has no drift | ✅ verified |
| Docker fresh-install validation passes | ✅ verified |

Every condition holds. Unlike the prior report, **there is no remaining
scoping judgment call** — the frontend build/dev image was brought to 0
Critical rather than excluded from the gate, closing the one open item
the owner asked to resolve. The only honestly-flagged limitation is that
GitHub Actions has not run on real GitHub infrastructure (no configured
remote); this is a documented verification gap, not a defect, and is
listed above accordingly rather than represented as tested.
