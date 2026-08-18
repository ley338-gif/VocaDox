# Contributing

## Branch / PR / commit workflow (spec §74)

- **Never commit directly to `main`.** All work happens on feature/phase
  branches (e.g. `phase-0-foundation`) and merges to `main` via pull
  request/review.
- Keep commits scoped and use clear messages describing *why*, not just
  *what*.
- Open a PR against `main` when a phase (or a meaningful slice of one) is
  ready for review; do not merge your own PR without review on anything
  beyond trivial scaffolding fixes.
- CI (`.github/workflows/ci.yml`) must pass before merge: backend
  lint/typecheck/test, frontend lint/typecheck/test, Docker builds, the
  OpenAPI TS-client drift check, and the license-compliance check.

## Local development

See the root [`README.md`](README.md) Quickstart for running the backend,
frontend, and full Docker Compose stack locally, and for the exact lint /
typecheck / test commands expected to pass before you open a PR.

## Scope discipline

This project is being built phase by phase (spec: 12 phases total). If
you're working on Phase N, resist implementing Phase N+1 functionality
"while you're in there" — log the idea in
[`docs/architecture/future-considerations.md`](docs/architecture/future-considerations.md)
instead. Each phase should end with its own validation report and an
explicit GO/NO-GO decision before the next one starts.

## License policy summary

Every dependency (Python, Node) and container image must be tracked in
`compliance/dependency-inventory.yml` / `compliance/container-inventory.yml`
with a real, verified license (via the PyPI/npm registry JSON APIs or the
project's official image registry — never guessed), classified against
`compliance/license-policy.yml`:

| Bucket            | Examples                                             | Meaning |
|--------------------|-------------------------------------------------------|---------|
| **Approved**        | MIT, Apache-2.0, BSD-2/3-Clause, ISC, PostgreSQL, OFL-1.1 | Use freely. |
| **Review required**  | MPL-2.0, LGPL-2.1/3.0                                 | Needs explicit sign-off recorded in `compliance/exceptions.yml` before use. |
| **Blocked**          | GPL, AGPL, SSPL, RSAL, BSL, Commons-Clause, proprietary, UNKNOWN | Not permitted. If you hit one, find an alternative — don't add an exception to bypass this without a real conversation about it. |

Run `python compliance/check_licenses.py` before proposing a new
dependency; it must exit 0. See
[`docs/licenses/license-policy.md`](docs/licenses/license-policy.md) for
the full prose rationale.

## AI models

If your change bundles or downloads an AI model (Phase 3+), add an entry to
`compliance/model-inventory.yml` with a *verified* license (not assumed)
before merging — see `docs/licenses/ai-models.md`.
