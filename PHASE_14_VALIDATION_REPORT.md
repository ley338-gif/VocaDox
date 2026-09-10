# VocaDox Phase 14 — Production Readiness 2.0 Validation Report

Date: 2026-09-10
Target release: 0.14.0
Scope baseline: `main` at `3ed96d7` plus the Phase 14 review stack listed below

## 1. Executive Summary

Phase 14 closes substantial gaps between the existing application and a
reproducible, reviewable on-premise release candidate. It adds strict dependency
locking, a fail-closed production topology, a full security/privacy sweep,
real-infrastructure and browser evidence-chain tests, source/security analysis,
SBOM generation, repository protection, live-transcript scaling evidence, a
recoverable PWA upload queue and a product-complexity decision.

The code is **not yet declared generally available or production ready**. At the
time of this report, PR #105 is merged and PRs #106–#115 are an independently
reviewable stack that has not been merged to `main`. A real target-site TLS
deployment, scheduled/off-host backup setup, restore drill on the target data
volume, populated-version upgrade rehearsal and production-scale AI quality/
latency benchmark remain operator/release gates.

Recommendation: **conditional release candidate, no unconditional GA approval**.
The conditions are listed in section 12.

## 2. Scope

Included:

- repository/version/release hygiene;
- locked Python, Node and container builds;
- separated development and production Compose topology;
- production configuration validation and proxy rate limits;
- review of Phase 13+ authentication, authorization, input, LLM, privacy and
  operational surfaces;
- real PostgreSQL 17.6 and Valkey evidence-chain integration coverage;
- Playwright evidence-source-to-transcript and permission-boundary coverage;
- CodeQL, repository secret scanning, container scanning and CycloneDX SBOMs;
- enforced `main` branch protection;
- live-transcript scaling benchmark and target architecture;
- PWA offline recording recovery and retry hardening;
- workspace/administration complexity review.

Explicitly excluded:

- new AI providers, integrations, document types, cloud sync, SaaS operation or
  analytics features;
- implementation of the proposed chunked live-transcript architecture;
- a large navigation redesign without usability evidence;
- operator-specific DNS, certificates, firewall, monitoring, backup scheduling
  or off-host storage.

## 3. Implemented Changes

| PR | Scope | State at report time |
| --- | --- | --- |
| #105 | repository status, version 0.14.0, changelog and release process | merged |
| #106 | locked Python/Node dependencies and strict CI/container installs | open review |
| #107 | guarded production deployment, proxy and configuration validation | open review |
| #108 | Phase 13+ security/privacy fixes and current threat model | open review |
| #109 | real PostgreSQL/Valkey evidence-chain golden path | open review |
| #110 | Playwright user/evidence/permission golden paths | open review |
| #111 | CodeQL, repository secret scan and four shipped-image SBOMs | open review |
| #112 | enforced `main` protection and staged-check policy | open review |
| #113 | live-transcript scaling benchmark and target architecture | open review |
| #114 | durable, retrying, crash-recoverable offline upload queue | open review |
| #115 | product-complexity review and terminology cleanup | open review |

The PRs are intentionally small/stacked. They must be reviewed and merged in
dependency order; a green descendant does not replace review of its ancestors.

## 4. Security Findings

The Phase 14 sweep found no Critical issue. It identified five High, seven
Medium and one Low issue in the reviewed Phase 13+ surface:

- High: issued-session survival after password reset/deactivation, recap bearer
  token re-exposure, cross-namespace image reads, GDT path/ZIP traversal and
  cleartext remote GDT API keys;
- Medium: weak protocol citation/output validation, unsafe image decoding/
  metadata retention, cross-organization template enumeration, cross-login
  offline queue exposure, absent production throttling, unbounded webhook
  response/target-age handling and indefinite signed-webhook replay acceptance;
- Low: missing explicit ICS/GDT parser caps.

The canonical IDs, attack descriptions, resolutions and review triggers are in
`docs/security/threat-model.md` (PR2-SEC-01 through PR2-SEC-13).

## 5. Resolved Findings

All 13 findings above have fixes and regression coverage in the Phase 14 stack:

- session generations revoke prior sessions after administrative identity
  changes;
- recap secrets are creation-only, hashed at rest, scope-restricted and
  no-cache;
- image and GDT inputs are namespace/path/size/decode constrained;
- remote bearer-key GDT transport requires HTTPS outside explicit localhost
  development;
- generated protocol citations use bounded structured output and real source
  resolution;
- service-account template reads are organization-filtered;
- queued recordings are user-bound, idempotent, single-flight and safely
  recoverable;
- Nginx applies dedicated login/public/API rate zones;
- webhook destinations and responses are repeatedly bounded and signed replay
  timestamps expire;
- ICS and GDT parsing enforce explicit resource caps.

These resolutions become release facts only after their PRs merge to `main`.

## 6. Accepted Risks

| Risk | Rating | Required control / reason for acceptance |
| --- | --- | --- |
| Public recap bearer links can be forwarded | Medium | short expiry, revocation, approved minimal content, secure recipient channel |
| DNS rebinding between validation and connection | Medium | admin-only configuration plus production egress firewall denying private/link-local/metadata targets |
| Raw offline audio is not application-encrypted in IndexedDB | Medium | managed encrypted devices and separate browser/OS profiles; avoid shared unmanaged endpoints |
| Voiceprints are biometric-like and threshold is not population-calibrated | Medium | lawful basis/consent, explicit enrollment, suggestion-only use and human confirmation |
| No aggregate organization/user storage quota | Medium | monitor storage and restrict upload permission; per-object/rate limits are not a quota substitute |
| Current live preview retranscribes the whole prefix | Medium | short-preview limitation; authoritative final pass remains separate; chunked target is not yet implemented |
| Citation existence does not prove semantic entailment | Medium | expose evidence and require human review for consequential use |
| FHIR output is not validated against a site-specific official profile | Low | receiving-system conformance testing before clinical interchange |
| Backups or an external LLM can expose all in-scope content if misconfigured | High | encryption/access control/off-host policy and an approved private provider are deployment obligations |
| Per-IP throttling can group users behind NAT | Low | tune for site topology without removing tight login/public limits |

## 7. Test Matrix

| Area | Validation | Result |
| --- | --- | --- |
| Backend static analysis | Ruff; mypy across 209 source files | pass |
| Backend behavior | 460 tests passed, 1 skipped | pass |
| Python dependencies | locked install; `pip-audit` | pass, no known vulnerability |
| Frontend static analysis | ESLint; TypeScript project check | pass |
| Frontend behavior | 62 Vitest tests | pass |
| Browser workflow | 2 Chromium Playwright golden paths | pass |
| Node dependencies | strict `npm ci`; `npm audit --audit-level=high` | pass, no vulnerability |
| GDT bridge | 20 tests | pass |
| Real infrastructure | PostgreSQL 17.6 + Valkey login-to-export evidence chain | pass in CI |
| Database migration | empty DB upgrade, downgrade to base, second upgrade | pass in CI |
| API contract | generated TypeScript/OpenAPI drift check | pass in CI |
| Licensing | direct, 505 transitive packages, containers and models | pass; 3 policy-reviewed, 0 blocked/unknown |
| Source security | CodeQL Python and JavaScript/TypeScript | pass on Phase 14 review stack |
| Secret detection | repository-content scan plus GitHub push protection | pass/enforced |
| Containers | backend, frontend runtime/dev, AI worker, GDT bridge builds | pass |
| Container security | Trivy scan of all shipped images plus frontend dev image | pass on Phase 14 review stack |
| Supply-chain artifacts | CycloneDX SBOM for backend, frontend, worker and GDT bridge | generated in CI |

The local full-suite evidence was repeated before each Phase 14 push. GitHub CI
is the authoritative independent record for each PR; branch protection requires
the configured baseline checks before merge.

## 8. Deployment Validation

Validated:

- production Compose does not publish PostgreSQL or Valkey;
- backend is reached through the TLS-ready reverse proxy topology;
- production startup fails for default database passwords, insecure session
  cookies, wildcard CORS and missing required secrets/paths;
- runtime, worker and connector images build from locked inputs;
- health checks, restart policies and named/bind volumes are declared;
- a dedicated backup bind path and one-shot configuration check are documented;
- development defaults are kept in the development stack.

Not validated here:

- a real customer host, DNS name, certificate chain/renewal, firewall or load
  balancer;
- sustained production traffic, real production-size media/model storage or
  operator alerting;
- a hosted external provider (none is required or introduced).

Therefore image/Compose readiness is validated, but target-site operational
readiness is not transferable without a site acceptance run.

## 9. Backup/Restore Validation

The existing disaster-recovery mechanism has an empirical PostgreSQL 17.6
restore-into-fresh-infrastructure record: database schema/data, media SHA-256 and
transcript content were restored, and the following migration was a no-op at
head. Phase 14 preserves this implementation and its real `pg_dump`/`pg_restore`
tooling; backend tests cover permission and failure recording, and all related
images still build.

Phase 14 did **not** repeat a destructive full restore drill against a target
production host or production-sized dataset. No automatic schedule, off-host
copy, rotation, encryption key custody or measured site RPO/RTO is shipped.
Before release at a site, operators must create and restore a fresh backup using
`docs/operations/disaster-recovery.md`, verify media checksums, configure a
schedule/off-host destination and record measured RPO/RTO.

## 10. Upgrade Validation

Validated:

- all migration revisions upgrade from an empty PostgreSQL database;
- all revisions downgrade to base and upgrade to head again in CI;
- the real-infrastructure golden path runs at current head;
- Phase 14 itself adds no irreversible application data migration;
- dependency installs fail on lock drift rather than silently re-resolving.

Not validated:

- an in-place, populated 0.13.x production database/media set upgraded to 0.14.0;
- application rollback after a data migration (database downgrade is not a
  substitute for restoring a pre-upgrade backup);
- mixed-version rolling deployment, which the single-host Compose design does
  not promise.

A release rehearsal must back up a representative 0.13.x copy, deploy 0.14.0,
run migrations and the evidence-chain smoke test, then prove rollback by restore.

## 11. Remaining Limitations

- PRs #106–#115 still require independent review and ordered merge.
- Chunked/overlapped live transcription is an accepted target, not implemented;
  the current 20/60-minute model implies approximately 60.5x/180.5x uploaded
  audio work. Real model/hardware wall time and WER are unmeasured.
- Offline queue marker upload is best-effort after the primary recording is
  confirmed; failed markers do not retain a second audio copy.
- Legacy ownerless IndexedDB records remain quarantined for explicit recovery/
  retention handling rather than being attributed or silently deleted.
- No aggregate storage quota, automated backup schedule, off-host transport,
  host monitoring, WAF or certificate automation is included.
- The conversation tab row remains dense. ADR-0046 defines an evidence-led
  progressive-disclosure target; no telemetry or disruptive redesign was added.
- FHIR receiving-profile conformance and site-specific GDT interoperability
  remain deployment acceptance work.

## 12. GA / Release Recommendation

Current decision: **NO-GA; conditional 0.14.0 release candidate.**

Approve a release only after all of the following are recorded:

1. independent review and ordered merge of PRs #106–#115 with required checks
   green on the final `main` commit;
2. a release tag built from that protected commit with published checksums and
   retained SBOM artifacts;
3. target-site production configuration check, TLS/DNS/firewall verification and
   login-to-export smoke test;
4. scheduled encrypted/off-host backup plus a successful fresh-infrastructure
   restore drill with measured RPO/RTO;
5. representative populated 0.13.x → 0.14.0 upgrade and restore-based rollback
   rehearsal;
6. site decisions for accepted privacy/security risks, especially offline audio,
   voiceprints, recap links, external providers and storage monitoring;
7. if long live previews are required for launch, real hardware/model latency and
   quality validation or implementation of the chunked target architecture.

Once these conditions pass, 0.14.0 is a reasonable on-premise release candidate.
Until then, describing the repository as unconditionally “production ready”
would exceed the available evidence.
