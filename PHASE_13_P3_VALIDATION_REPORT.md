# Phase 13 (Post-GA) — Stage P3 Validation Report

## Executive Summary

Stage P3 of the post-GA competitive roadmap (`[[vocadox-competitive-roadmap]]`)
is complete: both measures merged to `main`, each with all 7 required CI
checks green, each deployed and spot-checked live against the real dev
stack. **This is also the final stage** — all 12 roadmap measures across
Stages P0–P3 are now shipped. **Recommendation: GO.** See
`PHASE_13_ROADMAP_COMPLETION_SUMMARY.md` for the full-roadmap retrospective.

Same posture as the P0/P1/P2 reports: this documents what shipped, how
it was verified, and what remains honestly open, under the standing
autonomous GO (`[[github-workflow-autonomy]]`).

## Scope

| # | Measure | PR | Merge commit |
|---|---|---|---|
| P3-1 | One real Fachsystem integration: FHIR `DocumentReference` export | [#77](https://github.com/ley338-gif/VocaDox/pull/77) | `03d3f40` |
| P3-2 | Fact-level redaction + expiring Recap share links | [#78](https://github.com/ley338-gif/VocaDox/pull/78) | `d0a5a81` |

## P3-1 — FHIR `DocumentReference` export

- `docs/architecture/future-considerations.md`'s Phase 10 notes had
  deliberately documented four adapters (FHIR/HL7, PVS/KIS, CRM,
  meeting-platform) as architecture-only, no implementation. This
  measure implements exactly one real exception: `GET .../document/
  export?format=fhir` — a downloadable FHIR R4 `DocumentReference`
  resource, pure local file generation, no FHIR server contacted, no
  network call, no exception to ADR-0007.
- **Chosen over GDT** (the roadmap's other named option) — not on
  strategic grounds, but because FHIR R4's base `DocumentReference`
  shape is verifiable with confidence in this working environment (no
  internet access to check current, version-dependent GDT field-code
  tables against). Documented in ADR-0039 as a narrower, more honest
  reason than "FHIR is more modern."
- No real patient identity is ever claimed: `subject.display` is free
  text from a `PATIENT`-typed participant if one exists, omitted
  otherwise — never a resolvable `Patient` reference.
- Disclosed limitation: not validated against the official FHIR JSON
  Schema/StructureDefinition (no validation library was added).

## P3-2 — Fact-level redaction + expiring Recap share links

- **Redaction**: new `ExtractedFact.is_redacted`, orthogonal to
  `review_status` (a fact can be CONFIRMED/correct and redacted at the
  same time — redaction is about disclosure control, not correctness).
  The blackout lives in exactly one place —
  `app.intelligence.rendering.render_fact_statement`, the single shared
  renderer Document composition, search indexing, and Ask VocaDox
  citations already all go through — so redacted content is hidden
  everywhere at once, by construction. The internal, permission-gated
  `GET .../facts` view never calls that renderer, so a reviewer with
  `fact:read` always sees the real content and the audit trail
  (`FactRedactionEvent`, mirroring `FactCorrection`'s discipline)
  explaining why. New `fact:redact` permission, Manager/Reviewer only.
- **Share links**: `app.recap.public_router` — the first genuinely
  unauthenticated REST surface in this codebase, deliberately its own
  file. A `secrets.token_urlsafe(32)` token grants time-limited
  (24h/7d/30d) read access to a conversation's currently-approved
  recap, always serving live current-revision content. Creating a link
  requires `recap:approve`. New public frontend page at
  `/share/recap/:token`.
- **Disclosed assumption**: no rate limiting/abuse detection on the
  public endpoint — token entropy makes brute-forcing infeasible in
  practice, but a determined actor could still hammer one known token.
- A real cross-dialect bug was found and fixed while testing: SQLite
  round-trips `DateTime(timezone=True)` values as naive, unlike
  Postgres, which broke the share link's expiry comparison
  (`TypeError: can't compare offset-naive and offset-aware datetimes`)
  — fixed by normalizing before comparing, documented inline and in
  ADR-0040.

## Test / CI Summary

- Backend: `pytest -q` grew from 376 (P3-1, +2 FHIR export tests) → 385
  (P3-2, +4 redaction tests, +5 share-link tests) across the stage, 0
  failed. `ruff check .` and `mypy app` clean on every PR (195 source
  files by the end of P3-2).
- Frontend: `vitest run` stayed at 27 (unchanged — P3-1's new export
  link and P3-2's new redact button/share-link UI/public page were
  verified via `tsc -b --noEmit`/`eslint .`/`vite build`, matching this
  project's established precedent).
- `python compliance/check_licenses.py`: **PASS** on both PRs — zero
  new dependencies added anywhere in Stage P3.

## GitHub Actions

Both PRs' final commits show all 7 required checks green:

| Check | #77 (P3-1) | #78 (P3-2) |
|---|---|---|
| Backend (lint/typecheck/test) | PASS | PASS |
| Frontend (lint/typecheck/test/build) | PASS | PASS |
| Alembic migration (real Postgres) | PASS | PASS |
| OpenAPI TS client drift check | PASS | PASS |
| License compliance | PASS | PASS |
| Docker build | PASS | PASS |
| Container vulnerability scan (Trivy) | PASS | PASS |

## Live Deployment

P3-1 needed only a `backend`/`frontend` rebuild (no schema change), a
`GET /health/ready` check, and an unauthenticated-route spot-check
(`GET .../document/export?format=fhir` → `401`). P3-2 additionally ran
`docker compose run --rm migrate` for two new migrations
(`0021_fact_redaction`, `0022_recap_share_links`) and
`python -m app.identity.seed` to pick up the new `fact:redact`
permission, then three spot-checks: `GET /health/ready` (`200`), an
unauthenticated redact attempt (`401`), and an unauthenticated public
recap lookup with a nonexistent token (`404`, confirming the public
endpoint is genuinely live and correctly 404s rather than 500ing). No
exhaustive re-verification beyond that, per `[[feedback-verification-scope]]`.

## Known Limitations / Assumptions (disclosed, not blocking)

1. **P3-1**: only FHIR `DocumentReference` is implemented — not
   `Composition`, not a real FHIR REST push, not GDT (deferred, not
   rejected — see ADR-0039's Consequences). Full FHIR profile
   conformance (e.g. a German ISiK Basisprofil) is not machine-verified.
2. **P3-2**: no rate limiting on the public share-link endpoint. The
   `decided_by`-as-rationale gap from P1-3 (ADR-0033) is unrelated but
   worth re-noting: redaction hides a fact's content, it does not add
   the reasoning field that measure already disclosed as out of scope.
3. **CI process finding this stage**: a routine local `ruff check`
   scoped to specific paths missed a line-length violation in the P3-2
   migration file, and `compliance/dependency-inventory-transitive.yml`
   had drifted from an unrelated upstream `optuna` version bump between
   branch creation and merge. Both were real CI failures, fixed with a
   follow-up commit on the same PR before merge (see PR #78's commit
   history) — logged honestly rather than omitted, per this project's
   own Findings Register convention.
4. No independent security/privacy/threat-model sweep (Phase 12-style)
   was run across Stage P3's new surface area specifically — most
   notably, `app.recap.public_router` is a new unauthenticated attack
   surface that would benefit from one. This recommendation has now
   been carried across all four stage reports (P0 → P3) without being
   acted on within this autonomous run; it is the clearest concrete
   follow-up for whoever picks up work after this roadmap.

## Findings Register

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | A path-scoped local `ruff check` run missed a line-length violation in a newly-added migration file, only caught by CI's full-repo `ruff check .` | P3 (process) | **Fixed same session**, follow-up commit on PR #78 before merge |
| 2 | `compliance/dependency-inventory-transitive.yml` drifted from an unrelated upstream `optuna` (worker-scope, MIT, already-approved) version bump between branch creation and PR merge — CI regenerates and diffs this file fresh on every run, so any upstream drift during a long-lived branch surfaces as a failure regardless of what the PR itself touched | P3 (process, not product) | **Fixed same session** — regenerated via the documented Linux-Docker-with-CPU-torch-index recipe, same fix pattern as Stage P0's Finding #2 |

## Next

All 12 measures of the post-GA competitive roadmap (Stages P0 through
P3) are complete. See `PHASE_13_ROADMAP_COMPLETION_SUMMARY.md` for the
full retrospective and recommended next steps beyond this roadmap.
