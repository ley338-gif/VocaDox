# CI and repository security controls

Status verified on 2026-09-10 for `ley338-gif/VocaDox`.

## Source scanning

`.github/workflows/codeql.yml` analyzes Python and JavaScript/TypeScript on
changes targeting `main` and once per week. Results appear under GitHub
Security > Code scanning. A failing workflow or a new high-severity alert must
be triaged before release; suppressions require a reason in the alert and, when
architecturally relevant, an ADR.

## Secret scanning

GitHub provider-pattern secret scanning and push protection are enabled. At
verification time the repository reported zero open alerts. Non-provider
patterns and validity checks are disabled; an API attempt on 2026-09-10 left
both settings unchanged. The CI secret-scan job therefore runs Trivy's
secret-only filesystem scanner over the clean checkout and fails on any
finding. Gitleaks is intentionally not installed because this covers generic
patterns with the existing approved scanner rather than adding a second tool.

If an alert occurs, revoke or rotate the credential first, then remove it from
the repository history where appropriate. Merely deleting the current file is
not remediation. Do not paste the secret into an issue, pull request, or CI log.

## Container SBOMs

The container security job creates CycloneDX JSON documents for every shipped
image and stores them in the `container-sboms-<commit SHA>` workflow artifact
for 90 days. A missing or malformed SBOM fails CI. Release operators should
download the artifact for the tagged release commit and retain it with the
release evidence.

The four expected files are:

- `backend.cdx.json`
- `frontend.cdx.json`
- `worker.cdx.json`
- `gdt-bridge.cdx.json`

SBOM generation uses the same approved, digest-pinned Trivy image as the
container vulnerability gate. SBOMs inventory components; they do not replace
the vulnerability or license checks.
