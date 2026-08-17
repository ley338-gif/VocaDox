# 0003 — asyncpg over psycopg (license rationale)

## Status
Accepted

## Context
SQLAlchemy 2.0's async engine needs a Postgres DBAPI driver. The two
realistic candidates are `psycopg` (v3, the modern official driver) and
`asyncpg`. `psycopg` v3's core is licensed LGPL-3.0, which sits in this
project's *review required* bucket (spec §10) — not blocked, but not a
default choice either, and a driver used by literally every request path
is exactly the kind of pervasive dependency that should not carry an
unresolved licensing review if an equally capable alternative exists.
`asyncpg` is Apache-2.0 (verified via PyPI JSON API — see
compliance/dependency-inventory.yml), which is on the approved list
outright.

## Decision
Use `asyncpg` as the Postgres driver, wired through SQLAlchemy's async
engine (`postgresql+asyncpg://...`). This avoids taking on a
review-required dependency for infrastructure plumbing used everywhere.

## Consequences
- `asyncpg` is a mature, widely used, high-performance driver — no
  functional downside expected for this project's needs.
- SQLAlchemy's psycopg-specific dialect features (if any are ever needed)
  are unavailable; none are used in Phase 0 (no domain models exist yet).
- If a future requirement specifically needs `psycopg` (e.g. a feature only
  it supports), that would require a fresh ADR and a license review
  recorded in `compliance/exceptions.yml`.
