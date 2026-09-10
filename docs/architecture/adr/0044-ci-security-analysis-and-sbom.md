# ADR-0044: CI security analysis and shipped-image SBOMs

- Status: Accepted
- Date: 2026-09-10

## Context

VocaDox already gates linting, tests, dependency audits, container builds,
license compliance, and Trivy vulnerability scans. Phase 14 additionally asks
for source-code security analysis, secret detection, and reproducible software
bills of materials without adding redundant services or weakening the
on-premise runtime.

GitHub repository inspection on 2026-09-10 showed that provider-pattern secret
scanning and push protection are enabled and that there are no open alerts.
Non-provider patterns and validity checks remained disabled when an API update
was attempted, so native scanning alone does not cover every generic secret.
Adding Gitleaks would introduce a second dependency even though the already
approved Trivy version contains a filesystem secret scanner.

## Decision

- Run GitHub CodeQL advanced setup for Python and JavaScript/TypeScript on
  pushes and pull requests targeting `main`, plus a weekly scheduled scan.
  Both interpreted-language analyses use `build-mode: none` and the
  `security-extended` query suite. Action references are pinned to immutable
  commits; the job receives only read access plus the `security-events: write`
  permission required to publish results.
- Keep GitHub provider-pattern secret scanning and push protection, and run
  Trivy's secret-only filesystem scan over the clean checkout in CI. Any
  finding fails the job. Gitleaks is not added because this closes the generic
  pattern gap with an existing, approved and digest-pinned tool. Review native
  alerts in GitHub's Security view; never copy detected secret material into
  issues or logs.
- Use the already approved and digest-pinned Trivy image to generate one
  CycloneDX JSON SBOM for each shipped image: backend, frontend runtime, AI
  worker, and GDT bridge. Validate all four documents and retain them as one
  immutable-name workflow artifact for 90 days.
- Continue scanning the frontend development image for vulnerabilities, but do
  not publish an SBOM for it because it is not shipped.

## Consequences

The runtime and offline deployment gain no cloud dependency. CodeQL and
artifact retention are GitHub-hosted repository controls and are not part of
the deployed product. Release evidence now includes machine-readable component
inventories tied to the exact commit SHA. Gitleaks can be reconsidered only if
a documented coverage gap remains after the combined GitHub and Trivy checks.
