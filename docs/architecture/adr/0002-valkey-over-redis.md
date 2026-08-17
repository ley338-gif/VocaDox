# 0002 — Valkey over Redis, and backend abstraction naming

## Status
Accepted

## Context
The architecture needs a fast in-memory store for queueing, caching, and
coordination primitives (locks). Redis is the historically dominant choice,
but Redis Ltd. relicensed Redis (from Redis 7.4 onward) under
SSPL/RSAL-style dual licensing that is on this project's *blocked* list
(spec §10) for an on-premise product we distribute to customers. Valkey is
the Linux Foundation-governed fork that continues under BSD-3-Clause and is
wire-protocol compatible with Redis.

## Decision
Use Valkey (server: BSD-3-Clause, confirmed via container-inventory.yml;
Python client `valkey` on PyPI: MIT, confirmed via
compliance/dependency-inventory.yml) instead of Redis. All access goes
through three narrow Protocol interfaces defined in
`backend/app/platform/valkey/backends.py`: `CacheBackend`, `QueueBackend`,
`CoordinationBackend`, implemented by a single `ValkeyBackend` class in
`valkey_backend.py`. No domain package may import the `valkey` client
directly, and no class in the codebase may be named `RedisService` (or any
name implying a hard Redis dependency) — enforced by naming convention and
spot-checked in code review until an import-linter rule exists.

## Consequences
- Swapping the backing store later (e.g. back to open-source Redis if
  licensing changes again) means implementing one class, not touching
  domain code.
- Valkey is wire-compatible with Redis, so operationally this is a
  low-risk choice — existing Redis operational knowledge transfers.
- No worker/queue consumer exists yet in Phase 0 (workers ship later); the
  `QueueBackend` interface is validated only by unit tests against a fake
  today.
