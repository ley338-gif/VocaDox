# ADR-0043: Separate development and production deployment definitions

- Status: Accepted
- Date: 2026-09-10

## Context

The original Compose definition was intentionally optimized for local
development. It published PostgreSQL, Valkey, the API, and the Vite development
server; supplied `changeme`; and disabled the Secure session-cookie flag for
plain HTTP. Environment overrides could change some values, but nothing made a
mistaken production use fail closed.

VocaDox needs a reproducible on-premise production path without changing its
local-first architecture or introducing a cloud dependency.

## Decision

- Rename the existing definition to `deploy/compose.dev.yml`; the root wrapper
  continues to select it for convenient local development.
- Add a standalone `deploy/compose.prod.yml`. Only its TLS reverse proxy
  publishes host ports. PostgreSQL, Valkey, the API, workers, and static
  frontend stay on explicit Compose networks.
- Require the database password, TLS file paths, and separate backup path at
  Compose interpolation time. Do not provide production password fallbacks.
- Force production mode, Secure cookies, disabled database echo, and same-origin
  CORS defaults in the production definition. Use a production-specific CORS
  input name so Compose's automatic development `.env` loading cannot leak a
  localhost exception into production.
- Validate these assumptions again inside `Settings`. All backend-derived
  processes therefore reject known development passwords, missing/short
  passwords, insecure cookies, database echo, wildcard CORS, and non-HTTPS CORS
  origins when production mode is active. Validation errors hide input values
  so the database URL/password is not echoed into startup logs.
- Gate migrations and long-running application processes behind a one-shot
  configuration check, then retain service health checks and restart policies.
- Mount TLS material read-only, keep application data in named volumes, and use
  an explicit host path for backup artifacts.

## Consequences

Development remains a one-command workflow, with its unsafe conveniences
clearly confined to a file named `compose.dev.yml`. Production requires
deliberate operator input and valid TLS material before it can start. The same
validation also protects non-Compose deployments.

Certificate lifecycle, firewalling, host hardening, off-host backup transport,
release-image publication/signing, and deployment-specific GPU allocation
remain operator responsibilities. The extraction worker and model-manager need
an outbound-capable network for an administrator-managed Ollama endpoint or an
explicit model download; database services remain confined to the internal data
network.

## Alternatives considered

- One Compose file with environment-controlled overrides was rejected because
  development defaults could silently leak into production and the effective
  exposure was difficult to review.
- Publishing the backend and relying on a host-installed reverse proxy was
  rejected as the default because it unnecessarily expands the reachable
  surface and makes the supported topology less reproducible.
- Automatic certificate issuance was rejected because it introduces external
  connectivity and deployment-specific DNS assumptions. Mounted certificates
  keep the stack TLS-ready and on-premise neutral.
