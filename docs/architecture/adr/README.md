# Architecture Decision Records

MADR-style (Status / Context / Decision / Consequences), numbered sequentially. Never renumbered or deleted once merged — superseded ADRs get a new one that says so in its Context.

- [0001](0001-monorepo-domain-backend-layout.md) — Monorepo & domain-oriented backend layout
- [0002](0002-valkey-over-redis.md) — Valkey over Redis + backend abstraction naming
- [0003](0003-asyncpg-over-psycopg.md) — asyncpg over psycopg (license rationale)
- [0004](0004-evidence-first-data-model.md) — Evidence-first / three-layer data model
- [0005](0005-provider-abstraction-fakes.md) — Provider abstraction + fake-provider strategy
- [0006](0006-no-storybook-design-system.md) — No-Storybook design-system approach
- [0007](0007-zero-external-telemetry.md) — Zero-external-telemetry / on-prem-only stance
- [0008](0008-node-build-image-alpine.md) — Node build/dev image: Alpine over Debian, plus npm self-update
- [0009](0009-session-storage.md) — Server-side sessions in Valkey, not a Postgres table
- [0010](0010-argon2-password-hashing.md) — Argon2id (argon2-cffi) for password hashing
