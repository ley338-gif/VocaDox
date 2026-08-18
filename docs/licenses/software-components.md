# Software Components — License Inventory

Human-readable rendering of `compliance/dependency-inventory.yml` (direct
dependencies) and `compliance/dependency-inventory-transitive.yml` (full
resolved tree, 421 packages — regenerable via
`compliance/generate_transitive_inventory.py`, never hand-maintained).
Licenses were looked up live against the PyPI JSON API, the npm registry
JSON API, and (for the transitive tier) `pip-licenses`/`license-checker`
output against the actual installed dependency trees. Status is computed
against `compliance/license-policy.yml`. Last updated 2026-08-18 (Phase 0
remediation pass — see `PHASE_0_VALIDATION_REPORT.md` for the full story).

## Python (PyPI) — direct

| Package | Version installed | License | Status | Notes |
|---|---|---|---|---|
| fastapi | 0.141.1 | MIT | approved | |
| uvicorn | 0.52.3 | BSD-3-Clause | approved | |
| pydantic | 2.13.4 | MIT | approved | PyPI license fields empty; confirmed via GitHub LICENSE file |
| pydantic-settings | 2.15.0 | MIT | approved | added to the inventory during the final closeout pass (was a tracked gap) |
| sqlalchemy | 2.0.52 | MIT | approved | |
| alembic | 1.19.1 | MIT | approved | |
| asyncpg | 0.31.0 | Apache-2.0 | approved | Chosen over LGPL-3.0 `psycopg`, see ADR-0003 |
| valkey | 6.1.1 | MIT | approved | PyPI client package |
| python-multipart | 0.0.32 | Apache-2.0 | approved | |
| setuptools | 84.0.0 | MIT | approved | build-only; upgraded from a pre-83.0 pin to fix PYSEC-2026-3447 |
| ruff | 0.16.3 | MIT | approved | dev-only |
| mypy | 1.20.2 | MIT | approved | dev-only |
| pytest | 9.1.1 | MIT | approved | dev/test-only; upgraded from 8.x to fix PYSEC-2026-1845 |
| pytest-asyncio | 1.4.0 | Apache-2.0 | approved | dev/test-only; upgraded for pytest 9.x compat |
| httpx | 0.28.1 | BSD-3-Clause | approved | |
| pip-licenses | 5.5.5 | MIT | approved | compliance-tool-only, never shipped |
| pip-audit | 2.10.1 | Apache-2.0 | approved | compliance-tool-only, never shipped |

## Node (npm) — direct

| Package | Version installed | License | Status | Notes |
|---|---|---|---|---|
| react | 18.3.1 | MIT | approved | |
| react-dom | 18.3.1 | MIT | approved | |
| react-router | 7.18.2 | MIT | approved | |
| @tanstack/react-query | 5.101.4 | MIT | approved | |
| zod | 3.25.76 | MIT | approved | |
| vite | 7.3.6 | MIT | approved | dev-only; upgraded from 5.x to fix 4 npm-audit CVEs (see report) |
| @vitejs/plugin-react | 5.2.0 | MIT | approved | dev-only; version tied to the vite 7.x line |
| typescript | 5.9.3 | Apache-2.0 | approved | dev-only |
| eslint | 9.39.5 | MIT | approved | dev-only |
| vitest | 4.1.10 | MIT | approved | dev/test-only; upgraded from 2.x to fix a CRITICAL npm-audit CVE |
| @testing-library/react | 16.3.2 | MIT | approved | dev/test-only |
| openapi-typescript | 7.13.0 | MIT | approved | dev/codegen-only |
| lucide-react | 0.451.0 | ISC | approved | |
| @fontsource/inter | 5.3.0 | OFL-1.1 | approved | see `docs/licenses/fonts-assets.md` |
| license-checker | 25.0.1 | BSD-3-Clause | approved | compliance-tool-only, `--no-save`, never in package.json |

## Transitive tree (both ecosystems combined)

| Status | Count |
|---|---|
| Approved | 419 |
| Review required | 2 (`certifi`, `pathspec` — both MPL-2.0, dev-tooling-only, see `compliance/exceptions.yml`) |
| Blocked | 0 |
| Unknown | 0 |

## Containers

Rendering of `compliance/container-inventory.yml` — see that file for
full digests, purposes, and per-image remediation notes; see
`docs/architecture/adr/0003-asyncpg-over-psycopg.md` and
`docs/architecture/adr/0008-node-build-image-alpine.md` for the two base
image decisions this table reflects.

| Image | License | Status |
|---|---|---|
| postgres:16.6-alpine3.20 | PostgreSQL License | approved |
| valkey/valkey:8.0.2-alpine | BSD-3-Clause | approved |
| python:3.11-slim-trixie | PSF-2.0 (interpreter) | approved |
| nginx:1.31.3-alpine3.24 | BSD-2-Clause | approved |
| node:22-alpine3.24 | MIT (Node.js runtime) | approved |
| aquasec/trivy:0.56.2 *(scan tool only)* | Apache-2.0 | approved |

**Result**: 6/6 approved, 0 review required, 0 blocked, 0 unknown.

## Compliance / build tooling

| Tool | License | Purpose |
|---|---|---|
| pip-licenses | MIT | Python license inventory generation |
| pip-audit | Apache-2.0 | Python vulnerability scanning |
| license-checker | BSD-3-Clause | Node license inventory generation |
| Trivy (aquasec/trivy image) | Apache-2.0 | Container SBOM + vulnerability scanning |

## AI models

None bundled in Phase 0 — `compliance/model-inventory.yml` is empty. See
`docs/licenses/ai-models.md`.

## Result

**0 blocked, 0 unknown** across direct dependencies (32), the transitive
tree (421), and containers (6). Run `python compliance/check_licenses.py`
to re-verify this at any time — it regenerates nothing itself but gates
on whatever's currently in the `.yml` files; regenerate the transitive
file first with `compliance/generate_transitive_inventory.py` if the
lockfiles have changed since it was last generated.
