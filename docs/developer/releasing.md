# Release process

VocaDox uses Semantic Versioning. Until the production-readiness gates are
complete, versions remain below `1.0.0`; a version number alone is not a
production-readiness claim.

## Prepare a release

1. Create a release branch from an up-to-date `main`. Never prepare a release
   directly on `main`.
2. Choose one version and update all four version sources:
   `backend/pyproject.toml`, `backend/app/platform/version.py`,
   `frontend/package.json`, and `frontend/package-lock.json`. Regenerate
   `frontend/openapi.json` and its TypeScript client afterward.
3. Move the relevant `CHANGELOG.md` entries into a dated release section.
   Record known limitations; do not describe unverified capabilities as
   production-ready.
4. Run every repository-wide CI-equivalent check listed in `CONTRIBUTING.md`,
   including generated OpenAPI drift, dependency/license checks, container
   builds/scans, and the release-specific deployment, backup/restore, upgrade,
   integration, and browser-E2E gates that exist at that point.
5. Update `PHASE_14_VALIDATION_REPORT.md` with the exact evidence and a GO or
   NO-GO recommendation. A `1.0.0` release requires a GO with no unresolved
   Critical or High security finding.
6. Open a pull request. Merge only after required checks and review pass.

## Publish

After the release pull request is merged:

1. Create an annotated `vX.Y.Z` tag on the merge commit.
2. Build artifacts from that tag, never from an uncommitted working tree.
3. Download and retain the `container-sboms-<commit SHA>` artifact generated
   by CI for the tagged commit. Verify that it contains the four shipped-image
   CycloneDX documents listed in `docs/security/ci-security-controls.md`.
4. Publish release notes from the matching changelog section and link the
   validation report.
5. Verify image/application versions and the documented fresh-install and
   upgrade paths against the tagged artifacts.

If any publication or post-publication verification fails, do not move or
reuse the tag. Fix the issue through a new pull request and issue a new patch
version.
