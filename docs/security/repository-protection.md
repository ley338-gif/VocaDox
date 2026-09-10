# GitHub repository protection

Status verified on 2026-09-10 for `ley338-gif/VocaDox`.

## Active `main` protection

The `main` branch is protected by GitHub branch protection with administrator
enforcement. The active policy is:

- changes must arrive through a pull request;
- the branch must be up to date before merging;
- stale reviews are dismissed after a new push;
- all review conversations must be resolved;
- linear history is required;
- force pushes and branch deletion are disabled;
- squash is the only enabled merge method;
- administrators cannot silently bypass the branch rules.

The repository has one maintainer account, so the technical approval count is
zero. Requiring one GitHub approval would make every maintainer-authored change
unmergeable rather than provide independent review. The release process still
requires an independent review for non-trivial changes; this is a documented
process gate until a second reviewer account or team is available.

## Required checks

The following GitHub Actions checks are currently required and pinned to the
GitHub Actions app as their source:

- `Alembic migration (real Postgres)`
- `Backend (lint / typecheck / test)`
- `Container vulnerability scan (all shipped images + frontend build/dev)`
- `Docker build (backend + frontend + AI worker + GDT bridge)`
- `Frontend (lint / typecheck / test / build)`
- `GDT bridge (locked install / test)`
- `License compliance (direct + full transitive tree)`
- `OpenAPI TS client drift check`

Strict mode is enabled, so passing results from an outdated merge base do not
permit a merge.

## Staged follow-up while Phase 14 PRs are stacked

Several Phase 14 pull requests intentionally build on each other. A check must
not become mandatory before its workflow exists in `main`, because earlier
stack entries cannot report a future check. Update the protection after each
workflow lands:

1. after the real-infrastructure integration PR, require
   `Golden path (real PostgreSQL + Valkey)`;
2. after the Playwright PR, require
   `Browser golden path (Playwright / Chromium)`;
3. after the CI-security PR, require `Secret scan (repository content)`,
   `CodeQL (python)`, and `CodeQL (javascript-typescript)` or replace the two
   CodeQL job checks with GitHub's CodeQL code-scanning merge-protection rule;
4. after the stacked branches have been merged and no open PR uses them as a
   base, enable automatic deletion of merged branches.

Re-query the branch protection API after each update and record the result in
the Phase 14 validation report. Do not remove an existing required check to
work around a failing pull request.
