# Software Components — License Inventory

Human-readable rendering of `compliance/dependency-inventory.yml`. Licenses
were looked up live against the PyPI JSON API
(`https://pypi.org/pypi/<package>/json`) and the npm registry JSON API
(`https://registry.npmjs.org/<package>/latest`) on 2026-08-17. Status is
computed against `compliance/license-policy.yml`.

## Python (PyPI)

| Package | Version constraint | License | Status | Notes |
|---|---|---|---|---|
| fastapi | `>=0.141,<0.142` | MIT | approved | |
| uvicorn | `>=0.52,<0.53` | BSD-3-Clause | approved | |
| pydantic | `>=2.13,<3.0` | MIT | approved | PyPI license fields empty; confirmed via GitHub LICENSE file |
| sqlalchemy | `>=2.0,<2.1` | MIT | approved | |
| alembic | `>=1.19,<1.20` | MIT | approved | |
| asyncpg | `>=0.31,<0.32` | Apache-2.0 | approved | Verified per spec; chosen over LGPL-3.0 `psycopg` |
| valkey | `>=6.1,<6.2` | MIT | approved | Verified per spec (PyPI client package) |
| python-multipart | `>=0.0.32,<0.1` | Apache-2.0 | approved | |
| ruff | `>=0.16,<0.17` | MIT | approved | dev-only |
| mypy | `>=2.3,<2.4` | MIT | approved | dev-only |
| pytest | `>=9.1,<9.2` | MIT | approved | dev/test-only |
| pytest-asyncio | `>=1.4,<1.5` | Apache-2.0 | approved | dev/test-only |
| httpx | `>=0.28,<0.29` | BSD-3-Clause | approved | |

## Node (npm)

| Package | Version constraint | License | Status | Notes |
|---|---|---|---|---|
| react | `^19.2.8` | MIT | approved | |
| react-dom | `^19.2.8` | MIT | approved | |
| react-router | `^8.3.0` | MIT | approved | |
| @tanstack/react-query | `^5.101.4` | MIT | approved | |
| zod | `^4.4.3` | MIT | approved | |
| vite | `^8.2.1` | MIT | approved | dev-only |
| typescript | `^7.0.2` | Apache-2.0 | approved | dev-only |
| eslint | `^10.8.1` | MIT | approved | dev-only |
| vitest | `^4.1.10` | MIT | approved | dev/test-only |
| @testing-library/react | `^16.3.2` | MIT | approved | dev/test-only |
| openapi-typescript | `^7.13.0` | MIT | approved | dev/codegen-only |
| lucide-react | `^1.31.0` | ISC | approved | Verified per spec |
| @fontsource/inter | `^5.3.0` | OFL-1.1 | approved | Verified per spec; see `docs/licenses/fonts-assets.md` |

## Result

All 26 direct dependencies currently in the Phase 0 inventory resolve to
**approved** under `compliance/license-policy.yml`. No `review_required`,
`blocked`, or `unknown` licenses were found. Run
`python compliance/check_licenses.py` to re-verify this at any time.
