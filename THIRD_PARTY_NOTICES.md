# Third-Party Notices

VocaDox incorporates the following third-party software. This file lists
the ~31 **direct** dependencies for readability; the full **transitive**
dependency tree (421 resolved packages) is tracked separately in
`compliance/dependency-inventory-transitive.yml` (machine-readable,
regenerable via `compliance/generate_transitive_inventory.py`) — every
one of those is also license-approved or has a documented exception in
`compliance/exceptions.yml` (currently: `certifi`, `pathspec`, both
MPL-2.0, both dev-tooling-only). Run `python compliance/check_licenses.py`
to verify both tiers against the current policy. Last generated:
2026-08-18 (Phase 0 remediation pass).

No dependency or container image in either tier is licensed under a
copyleft-with-redistribution-obligation license (GPL/AGPL/SSPL) or an
unverified license — see `compliance/license-policy.yml` for the full
policy and `docs/licenses/license-policy.md` for the rationale.

## Python packages (PyPI)

| Package | License |
|---|---|
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| pydantic | MIT |
| sqlalchemy | MIT |
| alembic | MIT |
| asyncpg | Apache-2.0 |
| valkey | MIT |
| python-multipart | Apache-2.0 |
| ruff *(dev)* | MIT |
| mypy *(dev)* | MIT |
| pytest *(dev)* | MIT |
| pytest-asyncio *(dev)* | Apache-2.0 |
| httpx *(dev)* | BSD-3-Clause |
| setuptools *(build-only)* | MIT |
| pip-licenses *(compliance-tool-only)* | MIT |
| pip-audit *(compliance-tool-only)* | Apache-2.0 |

## Node packages (npm)

| Package | License |
|---|---|
| react | MIT |
| react-dom | MIT |
| react-router | MIT |
| @tanstack/react-query | MIT |
| zod | MIT |
| vite *(dev)* | MIT |
| typescript *(dev)* | Apache-2.0 |
| eslint *(dev)* | MIT |
| vitest *(dev)* | MIT |
| @testing-library/react *(dev)* | MIT |
| openapi-typescript *(dev)* | MIT |
| lucide-react | ISC |
| @fontsource/inter | OFL-1.1 (packaging the SIL Open Font License 1.1-licensed Inter typeface) |
| @vitejs/plugin-react *(dev)* | MIT |
| license-checker *(compliance-tool-only, not saved to package.json)* | BSD-3-Clause |

## Container base images

| Image | License |
|---|---|
| postgres:16.6-alpine3.20 | PostgreSQL License |
| valkey/valkey:8.0.2-alpine | BSD-3-Clause |
| python:3.11-slim-trixie | PSF-2.0 (interpreter); mixed OS-package licenses (Debian base layer) |
| node:20.18.1-bookworm-slim | MIT (runtime); mixed OS-package licenses (Debian base layer) |
| nginx:1.31.3-alpine3.24 | BSD-2-Clause (nginx license) |
| aquasec/trivy:0.56.2 *(scan tool only, never shipped)* | Apache-2.0 |

## Fonts and icons

- **Inter** (self-hosted via `@fontsource/inter`) — SIL Open Font License
  1.1. See `docs/licenses/fonts-assets.md`.
- **Lucide** icon set (via `lucide-react`) — ISC License. See
  `docs/licenses/fonts-assets.md`.

## AI models

None bundled in Phase 0. See `docs/licenses/ai-models.md` and
`compliance/model-inventory.yml`.

---

For the exact version pinned, the license source verified, and any notes
per dependency, see `compliance/dependency-inventory.yml` and
`compliance/container-inventory.yml`.
