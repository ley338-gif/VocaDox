# Phase 14 implementation plan

## Prompt review

The Phase 14 brief has the right safety boundaries and release gates, but the
full scope is too large for one reviewable change. Its final instruction to
inventory `main`, publish a short plan, and begin with the first small pull
request is the controlling execution boundary. Work is therefore split into
independently testable pull requests; later items are not considered complete
merely because they appear in this plan.

## Baseline inventory

- `main` at inventory time: `d648001` (protocol feature, PR #104).
- Product documentation and package metadata still described Phase 12 or the
  Phase 0 scaffold and used version `0.0.1`, despite substantial Phase 13+
  work. No release tags exist.
- The root Compose file includes `deploy/docker-compose.yml`, which is
  explicitly a development stack. PostgreSQL, Valkey, backend, and the Vite
  frontend publish host ports; the documented default database password and
  insecure development cookie setting make it unsuitable for production.
- Python dependencies are bounded but not locked. Node has a lockfile, while
  CI contains fallback installs that can silently repair a broken lock state.
- CI currently covers Ruff, Mypy, Pytest, a real-Postgres migration cycle,
  frontend lint/typecheck/test/build, OpenAPI drift, Docker builds, license
  compliance, dependency audits, and Trivy. It has no application golden-path
  Postgres/Valkey job, browser E2E, CodeQL, secret scan, or SBOM job.
- The threat model title and closing scope still describe a Phase 0 skeleton.
  Phase 13 reports explicitly carry forward a missing independent review of
  the new public recap endpoint and other new surfaces.
- Backup/restore tooling and operational documentation exist, but Phase 14
  still needs tagged-release deployment, restore, and upgrade evidence.
- GitHub API inspection found no protection and no repository ruleset on
  `main`. Merge commits, squash merges, and rebase merges are all enabled, and
  merged branches are not deleted automatically. A later focused repository
  protection change must add required checks/no-force-push/no-delete rules and
  select the intended merge policy; this inventory does not mutate repository
  settings.

## Pull-request sequence and acceptance criteria

1. **Repository and release hygiene**: align versions/status, introduce a
   changelog and release process, and record this plan. Verify metadata,
   backend checks, frontend checks, and OpenAPI drift.
2. **Dependency reproducibility**: adopt one Python lock strategy, make every
   Python install consume it, remove all `npm ci || npm install` fallbacks,
   and preserve license/audit coverage.
3. **Production deployment and guardrails**: add separate dev/prod Compose
   definitions, a TLS-ready reverse proxy, private data services, persistent
   volumes/backup paths, and fail-fast validation for secrets, cookies, CORS,
   passwords, and development-only settings.
4. **Security and privacy review**: review every Phase 13+ surface named in the
   brief, classify findings, update the threat model, and land Critical/High
   fixes before proceeding. Split unrelated fixes into focused pull requests.
5. **Real-infrastructure integration test**: exercise the evidence-chain
   golden path against PostgreSQL and Valkey with deterministic AI providers.
6. **Browser E2E**: add a small Playwright suite for the primary workflow and
   a normal-user permission boundary, centered on generated information to
   evidence source to transcript position.
7. **CI/repository protection**: add justified CodeQL, secret scanning, and
   SBOM controls; configure or precisely document `main` rulesets.
8. **P2 architecture and UX work**: benchmark live-prefix transcription,
   document the target architecture, harden the offline queue, and make only
   evidence-backed, low-risk navigation changes.
9. **Release validation**: validate fresh installation, production deployment,
   backup/restore, and upgrade, then complete `PHASE_14_VALIDATION_REPORT.md`.

Each pull request must keep existing APIs and evidence/audit/RBAC/organization
isolation invariants intact, add proportionate tests, run the full repository
checks, and avoid unrelated refactors.
