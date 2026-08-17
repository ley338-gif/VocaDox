# VocaDox — Phase 0 Validation Report

**Phase**: 0 — Architecture & Foundation
**Branch**: `phase-0-foundation` (never committed to `main`)
**Date**: 2026-08-17, remediated 2026-08-18
**Scope**: scaffolding only — no domain features (auth, conversations,
transcription, ...) are implemented. This report is the GO/NO-GO gate
before Phase 1 begins.

> **Revision note**: the original version of this report recommended GO
> based on direct-dependency licenses only. That recommendation was
> premature — it did not cover the *transitive* dependency tree (policy is
> UNKNOWN=BLOCKED, and that has to apply to every resolved package, not
> just the ~26 top-level ones) and left 5 known npm audit findings
> untriaged. This revision fixes both gaps, adds container SBOM/vulnerability
> scanning that wasn't done at all before, and applies a stricter,
> explicit GO/NO-GO rule (see Recommendation). Still Phase 0 — no domain
> feature work has started.

---

## Executive Summary

Phase 0 remains a working (not stubbed) monorepo scaffold — FastAPI
backend, React/Vite frontend with a token-driven design system,
Postgres+Valkey Docker Compose stack, Alembic migration framework, 7 ADRs,
and the documentation skeleton the plan specified. This remediation pass
added: full transitive-dependency-tree license scanning (421 resolved
packages, not just 26 direct ones), npm audit + pip-audit triage (all
findings resolved via version upgrades, re-verified at 0 vulnerabilities),
container SBOM/vulnerability scanning via Trivy against the actual shipped
runtime images (which drove real fixes — a stale/EOL base image and an
unnecessary build toolchain, not just paperwork), new CI security gates,
a lightweight architecture-boundary test, and a genuine clean-checkout
reproducibility test (not just claimed).

**Recommendation: GO for Phase 1**, under an explicit scoping decision
about build-stage-only container findings — see Recommendation for the
full rule-by-rule justification and the one judgment call that decision
rests on.

---

## Architecture

Unchanged from the original scaffold. Monorepo: `backend/`, `frontend/`,
`compliance/`, `docs/`, `deploy/`, `.github/workflows/`, root
`docker-compose.yml` wrapper (ADR-0001). Backend is domain-oriented:
`backend/app/<domain>/` per bounded context (17 domain packages, all
empty/documented placeholders in Phase 0), plus `platform/` and
`providers/`. Frontend is a Vite/React SPA with a `/design-system` route.

## Implementation

Unchanged from the original scaffold, plus one new file:
`backend/tests/test_architecture_boundaries.py` (see Security below). 36
backend Python source files (39 including the new test), all passing ruff
+ mypy.

## Design System

Unchanged — see `frontend/src/styles/tokens.css` and
`frontend/src/design-system/DesignSystemPage.tsx`.

## Database

Unchanged. `alembic upgrade head` re-verified against a fresh Postgres
container after the backend Dockerfile changed (see Containers below) —
still produces exactly one table, `alembic_version`.

## Valkey

Unchanged. `test_domain_packages_do_not_import_valkey_client_directly`
and `test_no_class_named_redis_service_anywhere` (new, see Security) now
enforce this invariant as a running test, not just a documented rule.

## Provider Architecture

Unchanged. `test_domain_packages_do_not_import_concrete_provider_implementations`
(new) now enforces "domain code depends on interfaces, not concrete
`Fake*`/`LocalFilesystemStorage` implementations" as a running test.

## OpenAPI

Unchanged mechanism. Re-verified after this remediation's changes (which
didn't touch any route): fetched a fresh `openapi.json` from a live
backend, regenerated `frontend/src/api/generated/schema.d.ts`, `git diff`
showed no drift.

## Tests

- **Backend**: 12 tests (`pytest -q`, up from 9) — the original 9 plus 3
  new architecture-boundary tests. All pass, including on a from-scratch
  clean checkout (see Reproducibility).
- **Frontend**: 3 tests (`vitest run`), unchanged, all pass — including on
  vite 7.3.6/vitest 4.1.10 (upgraded from 5.x/2.x during this remediation)
  and on a from-scratch clean checkout.

## CI

`.github/workflows/ci.yml` extended in this remediation:
- `backend` job: added a `pip-audit` step.
- `frontend` job: added an `npm audit --audit-level=high` step.
- `compliance` job: now regenerates `dependency-inventory-transitive.yml`
  from the actual resolved trees on every run (production-only Python
  tree, full dev Python tree, production-only npm tree, full npm tree),
  fails on drift against the committed file, then runs
  `check_licenses.py` against direct + transitive + containers + models.
- new `container-vulnerability-scan` job: builds the shipped
  `vocadox-backend` and `vocadox-frontend` (`runtime` target) images,
  scans both with Trivy, **fails the build on any CRITICAL finding**, and
  reports HIGH/MEDIUM/LOW non-blocking for visibility.
- `docker-build` job unchanged (image build + compose config validation).

**Not run in this session**: the actual GitHub Actions workflow was not
executed against GitHub's runners — every job's commands were run
manually (backend, frontend, compliance regeneration, Trivy scans) and
passed; the YAML was reviewed for correctness but not executed by the
real Actions engine. Same limitation as the original report.

## Security

`docs/security/threat-model.md` unchanged from the original scaffold
(upload handling, path traversal, secrets, auth boundaries, privacy
zones). New in this remediation:

- **Architecture boundary enforcement**
  (`backend/tests/test_architecture_boundaries.py`): 3 stdlib-`ast`-based
  tests, no new dependency added (`import-linter` was considered but
  judged not worth it while every domain package is still an empty
  placeholder — would have nothing real to check). Verifies domain
  packages never import the `valkey` client directly, never import a
  concrete provider implementation instead of its interface, and that no
  class anywhere is named `RedisService`. All 3 pass today and will start
  catching real violations the moment Phase 1 domain code lands.
- **Dependency vulnerability scanning**: `pip-audit` (Python) and
  `npm audit` (Node) both now run and both currently report **0 known
  vulnerabilities** — see the Security Findings section for the full
  before/after triage.
- **Container vulnerability scanning**: Trivy 0.56.2 (Apache-2.0 — license
  checked before use; Docker Scout was evaluated and rejected for being
  proprietary-licensed under the Docker Subscription Service Agreement)
  scanned via its pinned official image. Found real issues that got
  genuinely fixed — see Security Findings.

## Privacy

Unchanged from the original scaffold.

## Dependencies

Two tiers now, both regenerated from real tooling output, never hand-typed:

**Direct** (`compliance/dependency-inventory.yml`, 31 packages — the
original 26 plus `pip-licenses`, `pip-audit`, `license-checker`,
`@vitejs/plugin-react`, and `setuptools`, added/tracked during this
remediation as build/compliance-tooling dependencies):

| Status | Count |
|---|---|
| Approved | 31 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

**Transitive** (`compliance/dependency-inventory-transitive.yml`, 421
resolved packages — the full dependency tree, not just direct ones,
generated by `compliance/generate_transitive_inventory.py` from real
`pip-licenses`/`license-checker` output against the actual installed
trees, both production-only and full-dev, for both ecosystems):

| Status | Count |
|---|---|
| Approved | 419 |
| Review required | 2 |
| Blocked | 0 |
| Unknown | 0 |

The 2 review-required transitive packages are `certifi` and `pathspec`
(both MPL-2.0, both dev-tooling-only transitive deps of `pip-audit`/`mypy`,
never shipped) — each has an explicit sign-off recorded in
`compliance/exceptions.yml` (unmodified, dev-only usage, no MPL-2.0
obligation triggered). No package was approved "because its parent is
approved" — every one of the 421 was individually classified against its
own resolved license string, including a handful of exotic-but-legitimate
permissive licenses discovered along the way (`MIT-0`, `BlueOak-1.0.0`,
`CC0-1.0`, `CC-BY-3.0`/`4.0`, `PSF-2.0`) that got added to
`license-policy.yml`'s approved list with per-package provenance notes
rather than silently waved through.

## Containers

`compliance/container-inventory.yml`, 6 images (the original 5 plus
Trivy itself, tracked as a scan-tool-only dependency):

| Status | Count |
|---|---|
| Approved | 6 |
| Review required | 0 |
| Blocked | 0 |
| Unknown | 0 |

Two base images were switched during this remediation, both driven by
real Trivy findings, not speculatively:
- **Backend**: `python:3.11.10-slim-bookworm` → `python:3.11-slim-trixie`.
  Bookworm had CRITICAL CVEs (sqlite3, util-linux) with **no fix
  backported to bookworm on any release** (confirmed against the Debian
  security tracker — bookworm-security still shows "vulnerable"; sqlite3's
  CVE is marked "no-dsa"). Trixie carries fixed versions.
- **Frontend**: `nginx:1.27.3-alpine3.20` → `nginx:1.31.3-alpine3.24`.
  Alpine 3.20 was flagged by Trivy as EOL/unsupported; 3.24 is current.

## Licenses

Four independent inventories, each counted separately (never summed into
one blended number — `dependency-inventory-transitive.yml` is a superset
of `dependency-inventory.yml`, so adding them would double-count):

| Inventory | Approved | Review required | Blocked | Unknown |
|---|---|---|---|---|
| Direct dependencies (31) | 31 | 0 | 0 | 0 |
| Transitive dependencies (421) | 419 | 2 | 0 | 0 |
| Containers (6) | 6 | 0 | 0 | 0 |
| Models (0) | 0 | 0 | 0 | 0 |

`compliance/check_licenses.py` (extended in this remediation to also load
and gate on the transitive inventory) — actually run, exit code 0:

```
Summary by category (never summed together)
category      approved   review_required   blocked   unknown
direct        31         0                 0         0
transitive    419        2                 0         0
containers    6          0                 0         0
models        0          0                 0         0

result: PASS (no blocked or unknown-licensed items)
```

**0 blocked, 0 unknown across all four inventories.** `THIRD_PARTY_NOTICES.md`
and `docs/licenses/` were not yet updated to reflect the transitive tier
in this pass — flagged in Known Limitations.

## Security Findings

Every CRITICAL/HIGH finding below was individually triaged (package,
version, direct/transitive, prod/dev, advisory, fix, action taken) — full
detail in `compliance/dependency-inventory.yml` notes,
`compliance/container-inventory.yml` notes, and this section. Severity
buckets follow the source tool's own rating (npm audit / pip-audit / Trivy).

### Application dependencies (npm audit + pip-audit)

| Severity | Found | Disposition |
|---|---|---|
| Critical | 1 (`vitest` — GHSA-5xrq-8626-4rwp, Vitest UI arbitrary file read) | **Resolved** — vitest 2.1.9 → 4.1.10 |
| High | 1 (`vite` — GHSA-4w7w-66w2-5vf9 path traversal + 2 more) | **Resolved** — vite 5.4.21 → 7.3.6 |
| Moderate | 3 (`esbuild`, `vite-node`, `@vitest/mocker` — transitive of the above) | **Resolved** — same upgrade |
| Low/Moderate | 2 (`pytest` — PYSEC-2026-1845 tmpdir handling; `setuptools` — PYSEC-2026-3447 MANIFEST.in bypass) | **Resolved** — pytest 8.4.2 → 9.1.1 (+ pytest-asyncio → 1.4.0 for compat); setuptools → 84.0.0 |

Re-verified after fixes: `npm audit` → **0 vulnerabilities**; `pip-audit`
→ **No known vulnerabilities found**. Both direct-dependency version
constraints in `dependency-inventory.yml` were updated to match, with the
GHSA/PYSEC IDs and rationale recorded inline. The vite upgrade initially
attempted 8.2.1, which pulled in the new Rolldown bundler and hit a known
npm cross-platform-optional-dependency bug inside the Docker build
(`npm/cli#4828`) — backed off to 7.3.6, which fixes the same CVEs without
that bundler change; see the `vite` entry's notes for the full story.

### Container images — shipped runtime images only

("Shipped" = `vocadox-backend` — backend/Dockerfile's only stage — and
`vocadox-frontend`'s `runtime` target, i.e. exactly what a customer
deploys. See the Node build-stage caveat below.)

| Image | Before remediation | After remediation |
|---|---|---|
| `vocadox-backend` | 23 CRITICAL, 225 HIGH | **0 CRITICAL**, 8 HIGH |
| `vocadox-frontend` (`runtime`) | 3 CRITICAL, 35 HIGH | **0 CRITICAL, 0 HIGH** (0 of any severity) |

Backend fix path (three steps, each independently verified against a
rebuilt + rescanned image, and smoke-tested with a live health check
after each change):
1. Removed `apt-get install build-essential` — verified every runtime
   dependency (incl. `asyncpg`) installs from prebuilt manylinux wheels,
   so no C/C++ toolchain is needed at all. This alone dropped the
   toolchain's `linux-libc-dev`/`binutils`/etc. findings (~157 of the 225
   original HIGH findings traced to `linux-libc-dev` alone).
2. Switched base image bookworm → trixie (see Containers) + added
   `apt-get upgrade` for within-release security patches — dropped
   CRITICAL from 10 to 4 (bookworm) then to 4 again on trixie (same 4
   perl CVEs, unfixed on any current Debian release).
3. Purged `perl-base` entirely from the final image — verified via
   `apt-cache rdepends`/direct testing that Python/pip work fine without
   it (it's marked "Essential" by Debian convention but nothing in our
   runtime path calls it). This eliminated the last 4 CRITICAL findings.

Remaining 8 HIGH on `vocadox-backend`, each with an explicit documented
acceptance (full text in `backend/Dockerfile`'s comments and
`container-inventory.yml`):

| Package(s) | CVE(s) | Why accepted |
|---|---|---|
| `gzip`, `libacl1`, `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` (6 findings) | CVE-2026-41992, CVE-2026-54369, CVE-2025-69720 | Debian OS utilities never invoked by our Python ASGI process (no TTY/ACL/gzip-CLI usage in the app); **no fix published on any current Debian release**; not removed like perl because `libtinfo6` is a reverse-dependency of `util-linux` and other base-image tooling — removing it risks destabilizing the base image without further testing than this pass had budget for. |
| `msgpack` 1.1.2 (GHSA-6v7p-g79w-8964) | fix 1.2.1 exists | This is **pip's own internally vendored copy** (`pip/_vendor/msgpack`), used only by pip's internal operations, never by our application code or exposed to any external input path. We don't control pip's vendoring; not independently patchable without forking pip. |
| `setuptools` 70.3.0 (CVE-2025-47273) | fix 78.1.1+ | **Could not reproduce on disk** — exhaustive filesystem search (`find / -iname '*setuptools*'`, `python3 -c "import setuptools; print(setuptools.__version__)"`) confirms only setuptools 84.0.0 (already patched, well above the fix version) is actually present in the built image. Treated as a probable Trivy scan artifact and explicitly flagged as such rather than silently dismissed. |

**Node build-stage image** (`node:20.18.1-bookworm-slim` —
frontend/Dockerfile's `base`/`build`/`dev` stages): 8 CRITICAL, 48 HIGH,
**not remediated**. This image's filesystem is entirely discarded by the
multi-stage build (the `runtime` stage `COPY`s only the built static
`dist/` output out of it) and is otherwise used only as the local
docker-compose `dev` service — never deployed to a customer. Re-checked
against a freshly-pulled (non-pinned) `node:20-bookworm-slim` and it still
showed 8 CRITICAL — unlike python/nginx, this isn't a stale-pin issue; no
non-EOL Debian-based alternative is currently published upstream for the
official `node:20` image line. **Tracked as an open risk, explicitly
excluded from the shipped-image scope** — see Recommendation for how this
affects the GO/NO-GO reading.

## Documentation

Unchanged from the original scaffold, except this report. **Not yet
updated in this pass**: `THIRD_PARTY_NOTICES.md` and `docs/licenses/*.md`
still reflect only the direct-dependency tier, not the new transitive
inventory or the container base-image changes — flagged below.

## Reproducibility

Checklist, now with the previously-unverified items actually executed
(not just claimed) in this remediation pass:

```
[x] clean git checkout tested — VERIFIED (`git clone --branch
    phase-0-foundation` into a scratch directory; committed state builds
    and tests identically to the working tree)
[x] no locally cached Python dependency required — VERIFIED (fresh venv,
    `pip install --cache-dir <empty-dir> --no-cache-dir -e ".[dev]"`
    against the clean clone; all 12 backend tests, ruff, and mypy pass)
[x] no locally cached npm dependency required — VERIFIED (`npm install
    --cache <empty-dir>` against the clean clone; 0 vulnerabilities;
    eslint/tsc/vitest/build all pass)
[x] empty Docker volumes tested — VERIFIED (`docker compose down -v` then
    `up` against the updated Dockerfiles; fresh named volumes)
[x] fresh PostgreSQL tested — VERIFIED (fresh postgres container; only
    `alembic_version` exists after migration)
[x] fresh Valkey tested — VERIFIED (fresh valkey container; `/health/ready`
    reports `valkey: true`)
[x] generated OpenAPI client matches repository — VERIFIED (regenerated
    from a live backend after this remediation's changes; `git diff`
    clean)
[x] no uncommitted generated files — VERIFIED (`git status --short`
    clean after the final commit)
```

Every item is now genuinely verified — none are estimated or assumed.
The Docker fresh-install cycle was re-run in full after the Dockerfile
changes (not just reused from before this remediation): `docker compose
down -v && docker compose build --no-cache && docker compose up -d` →
`/health/live` 200, `/health/ready` 200 (`database: true, valkey: true`),
`alembic upgrade head` succeeded. The frontend production image was
additionally rebuilt and smoke-tested standalone (`docker build --target
runtime` + `docker run`, 200 on `/` and `/health`).

## Known Limitations

- **`THIRD_PARTY_NOTICES.md` / `docs/licenses/*.md` are stale** — they
  document the direct-dependency tier only, predating this remediation's
  transitive inventory and container base-image swaps. Should be
  regenerated before Phase 1 sign-off, even though the underlying
  machine-readable data (`compliance/*.yml`) is current and passing.
- **OS-package-layer license identification** inside base container
  images is still not exhaustively audited (only the primary
  runtime's license is recorded) — same limitation as before, now
  narrower in practice since Trivy's vulnerability scan did enumerate the
  actual OS packages present (just not systematically cross-checked for
  license, only for CVEs).
- **GitHub Actions itself was not executed** on GitHub's infrastructure —
  same limitation as the original report; all new CI steps were run
  manually and passed, but not by the real Actions engine.
- **Node build-stage image vulnerabilities were not remediated** — see
  Security Findings. This is a deliberate scoping decision (build-stage/
  dev-only, never shipped), not an oversight, but it is real residual
  exposure for anyone running the local dev Docker Compose stack.
- **8 HIGH findings remain accepted (not fixed)** on the shipped backend
  image — see Security Findings' disposition table. All have no upstream
  fix currently available except `msgpack` (pip-internal, not
  independently patchable) and the likely-artifactual `setuptools`
  finding.
- **The `ncurses`/`gzip`/`libacl1` family of accepted findings was not
  investigated for removability** the way `perl-base` was (time-budget
  tradeoff within this remediation pass) — `libtinfo6` has real reverse
  dependencies from other base-image tooling, so a careful
  minimal-image exercise (possibly moving toward a distroless or
  further-trimmed base) is a reasonable Phase 1 follow-up rather than
  something to rush here.

## Open Risks

1. **Node build-stage/dev image vulnerabilities** (8 CRITICAL, 48 HIGH,
   `node:20.18.1-bookworm-slim`) — real exposure for local development
   only, not for anything shipped to a customer. No non-EOL upstream
   alternative currently exists for `node:20`; revisit when one does, or
   consider an Alpine-based node image for the dev/build stages.
2. **8 accepted HIGH findings on the shipped backend image** — no
   upstream fix exists for 6 of them on any current Debian release;
   revisit whenever the base image is next refreshed or Debian ships a
   backport.
3. **Compliance/license docs (`THIRD_PARTY_NOTICES.md`, `docs/licenses/`)
   need a follow-up pass** to reflect the transitive inventory and
   container changes made in this remediation — the underlying data is
   correct and gating in CI; the human-readable docs are what's stale.
4. **Privacy-zone retention policy still undecided** (unchanged from the
   original report, `future-considerations.md`).
5. **No automated architecture-boundary enforcement beyond the new
   targeted tests** — `test_architecture_boundaries.py` checks three
   specific invariants via `ast`, not a general dependency-graph linter;
   sufficient for Phase 0's all-placeholder domains, likely to need
   strengthening (or an `import-linter` adoption) once real domain code
   accumulates in Phase 1+.

## Architecture Deviations

Same as the original report (react-router pinned to 7.x for stability,
license unaffected), plus: `vite` ended up pinned to 7.3.6 rather than the
originally-planned 5.x line or the initially-attempted 8.x line, purely as
a consequence of the npm audit remediation — documented inline in
`dependency-inventory.yml`. No functional/architectural impact.

## Deferred Items

Unchanged from the original report — all domain feature logic, real
provider engine integrations, the worker pipeline, and AI model bundling
remain Phase 1+ work. `docs/architecture/future-considerations.md` gains
no new entries in this remediation pass beyond what's already tracked in
Open Risks above.

## Git Status

Branch: `phase-0-foundation`. `git status --short` is clean (no untracked
or modified files) after the final commit. `git diff --check` reports no
whitespace errors. No `.env` file is tracked, no `node_modules/`, no
Python `.venv/`, no build output directories, and
`compliance/_raw_*.json`/`_raw_*.txt`/`_container-scan/` (regenerable scan
intermediates) are gitignored rather than committed.

## Recommendation

**GO for Phase 1**, applying the rule exactly as specified: *GO only if
blocked licenses = 0 AND unknown licenses = 0 (across direct, transitive,
containers, models) AND no unresolved Critical finding AND no unresolved
High finding without an explicit documented acceptance AND all Phase-0
tests still pass.*

Checked against the shipped runtime images (`vocadox-backend`,
`vocadox-frontend`'s `runtime` target) and the four license inventories:

- Blocked licenses: **0** (direct, transitive, containers, models — all confirmed)
- Unknown licenses: **0** (same, all confirmed)
- Unresolved Critical findings: **0** (23→0 backend, 3→0 frontend, both
  independently verified by rescanning the actual built images after
  each fix)
- Unresolved High findings without documented acceptance: **0** — 8
  remain on the backend image, every one individually justified in
  Security Findings' disposition table and in `container-inventory.yml`
- All Phase-0 tests pass: **yes** — 12/12 backend, 3/3 frontend, plus a
  full fresh-install Docker cycle and a from-scratch clean-checkout
  reproducibility test, all green

**The one judgment call this GO rests on**: the rule is applied to the
*shipped* runtime images, not the `node:20.18.1-bookworm-slim` build-stage/
dev-only image, which still has 8 CRITICAL findings that were not
remediated (see Security Findings and Open Risk #1). This scoping —
runtime image contents vs. build-stage-only packages discarded by the
multi-stage build — was explicitly sanctioned by this remediation's own
brief ("note ... that this covers runtime image contents, not
build-stage-only packages that get discarded in the multi-stage build").
If that scoping is *not* accepted and the node build-stage image is held
to the same bar as the shipped images, the correct call reverts to
**NO-GO** until either an upstream non-EOL node:20 base becomes available
or the dev/build toolchain is moved to a different, currently-clean base
image. Flagging this explicitly rather than deciding it unilaterally.
