# 0008 — Node build/dev image: Alpine over Debian, plus npm self-update

## Status
Accepted

## Context
The Phase 0 remediation pass's own validation report flagged an open
judgment call: `node:20.18.1-bookworm-slim` (used for
`frontend/Dockerfile`'s `base`/`build`/`dev` stages) carried 8 CRITICAL /
48 HIGH Trivy findings. It was initially excluded from the shipped-image
GO/NO-GO gate on the reasoning that its filesystem never reaches the
`runtime` stage and the `dev` stage is local-development-only — but the
owner asked for this to be resolved properly rather than waved away,
since the `dev` target is still something a developer runs, and "discarded
by multi-stage build" isn't the same as "risk-free."

## Decision
Evaluated every currently-supported official Node 22 LTS image variant:

| Image | CRITICAL | Root cause |
|---|---|---|
| `node:22-bookworm-slim` | 6 | `perl-base` (Debian ships perl on every release; same issue the backend hit and fixed by switching to trixie) |
| `node:22-trixie-slim` | 5 | `perl-base` again — Debian bookworm *and* trixie both ship a perl with 4 CVEs that have no fix on any current Debian release (verified against the security tracker) |
| `node:22-alpine3.21` / `3.22` / `3.24` | 5 | **Not perl** — Alpine doesn't ship perl at all. All 5 were npm's own vendored copies of `tar`/`brace-expansion`/`ip-address`/etc., bundled inside the Node.js Alpine image's pre-installed npm. |

Alpine's findings, unlike Debian's, were all things we could actually fix:
running `npm install -g npm@latest && npm cache clean --force` as the
first step in `frontend/Dockerfile`'s `base` stage replaces npm's
vendored dependency copies with current ones. Verified this drops the
image to **0 CRITICAL, 3 HIGH** (residual: `brace-expansion` and
`ip-address`, still vendored inside npm's own dependency tree even at
`npm@latest` — see `container-inventory.yml` for the accepted-risk
writeup).

Switched `frontend/Dockerfile` to `node:22-alpine3.24` (pinned by tag +
digest) with the npm self-update step. Verified end-to-end after the
switch: `npm install`/`lint`/`typecheck`/`test`/`build` all pass inside
the image, the multi-stage `runtime` target still builds and serves via
nginx correctly (not the Vite dev server), and no application dependency
had to change to make this work.

## Consequences
- The backend and frontend build images now use different base
  distributions (Debian trixie vs. Alpine) — acceptable; they're
  independent images with independent toolchains, and "same distro
  everywhere" was never a stated goal.
- Alpine uses `musl` libc instead of `glibc`; this is the same
  battle-tested official Node Alpine image variant used broadly across
  the ecosystem, and Phase 0's frontend build (Vite, esbuild-family
  tooling, standard npm packages) has no native-binary incompatibility
  with it — verified by actually running the full build/lint/typecheck/
  test suite inside the image, not assumed.
- The `npm install -g npm@latest` step adds a small amount of build time
  and a step to keep an eye on (a future npm major version bump happens
  "for free" on every rebuild) — acceptable given it directly resolves
  the image's CRITICAL findings and self-heals as npm ships further
  patches upstream.
- 3 residual HIGH findings (npm's own vendored `brace-expansion`,
  `ip-address`) remain, with no further fix available from us short of
  patching npm's internals — documented as an accepted risk, same
  treatment as the backend image's accepted pip-internal `msgpack`
  finding (ADR context: `container-inventory.yml`).
