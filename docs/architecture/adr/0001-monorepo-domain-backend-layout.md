# 0001 — Monorepo & domain-oriented backend layout

## Status
Accepted

## Context
VocaDox needs a repo structure that (a) keeps frontend, backend, deployment,
and compliance artifacts easy to review together during Phase 0's
architecture review, and (b) sets up the backend so each future domain
(conversations, transcription, evidence, ...) has an obvious, isolated home
as it's implemented phase by phase (spec §7).

## Decision
Single monorepo with top-level `frontend/`, `backend/`, `compliance/`,
`docs/`, `deploy/`, `.github/workflows/`. Inside `backend/app/`, one package
per domain (`identity/`, `conversations/`, `evidence/`, ...) plus two
cross-cutting packages: `platform/` (config, logging, db, valkey, health —
infrastructure concerns only) and `providers/` (external-engine
abstractions). Domain packages may depend on `platform` and `providers`;
`platform`/`providers` never depend on a domain package; domain packages do
not depend on each other's internals (only through their public API, once
those exist).

Phase 0 ships every domain package as an empty, documented placeholder
(`__init__.py` + `README.md` stating which phase implements it) — see each
package's README for details.

## Consequences
- Reviewers can navigate straight to the domain they care about.
- The platform/providers vs. domain boundary is enforced by convention now
  and can be enforced by import-linter rules later if drift becomes a
  problem.
- A monorepo means frontend and backend CI jobs share one repo's CI
  pipeline; kept simple in Phase 0 with independent job steps rather than a
  build-graph tool (Nx/Turborepo) — revisit if the repo grows enough to
  need incremental/cached builds.
