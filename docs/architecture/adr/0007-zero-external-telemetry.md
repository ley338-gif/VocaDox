# 0007 — Zero-external-telemetry / on-premise-only stance

## Status
Accepted

## Context
VocaDox is an on-premise product handling sensitive conversation content
(potentially clinical/personal data). Any silent outbound telemetry,
crash-reporting SaaS, or analytics SDK would (a) risk leaking sensitive
data outside the customer's infrastructure and (b) contradict the
on-premise trust model the product is sold on.

## Decision
No dependency that phones home by default is used anywhere in the stack.
Concretely for Phase 0: no analytics SDKs, no third-party error-tracking
SaaS, no CDN-hosted fonts/icons/scripts (fonts are self-hosted via
`@fontsource/inter`, icons via `lucide-react`, both bundled at build time —
see `docs/licenses/fonts-assets.md`), and the FastAPI app makes no
outbound network calls of its own in Phase 0. Health/readiness checks only
talk to the customer's own Postgres/Valkey. Any future telemetry (e.g.
opt-in crash reporting) must be explicitly opt-in, configurable to point at
customer-controlled infrastructure, and get its own ADR.

## Consequences
- Simplifies the compliance story: nothing to audit for "does this ship
  customer data off-prem."
- Debugging/observability is Phase 0 stdlib-logging + `/health/*` only; a
  fuller observability stack (metrics, tracing) is deferred and, when
  added, must default to on-prem-only sinks (e.g. self-hosted Prometheus).
- Self-hosting fonts/icons adds a small amount of bundle size versus a CDN,
  accepted as the cost of the zero-external-calls guarantee.
