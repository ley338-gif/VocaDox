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
- [0011](0011-source-media-separation.md) — Conversation/source-media separation and immutable-source integrity
- [0012](0012-chunked-upload-decision.md) — Recording upload: single finalize request, not server-side chunking
- [0013](0013-media-storage-layout.md) — Media storage layout: namespaced opaque keys, never client paths
- [0014](0014-media-normalization-and-metadata.md) — Media normalization stays a NoOp; mutagen rejected for metadata
- [0015](0015-retention-and-deletion-semantics.md) — Retention foundation and soft-delete vs. physical deletion
- [0016](0016-speech-provider-selection.md) — Speech-to-text provider and model selection
- [0017](0017-diarization-provider-selection.md) — Diarization provider and model selection
- [0018](0018-model-installation-strategy.md) — Model installation strategy: downloaded-at-install-time, not bundled
- [0019](0019-ffmpeg-normalization.md) — Media normalization via a real transcoding engine (FFmpeg, LGPL build)
- [0020](0020-worker-topology.md) — Worker topology: two role-parameterized services, one image
- [0021](0021-word-timing-storage.md) — Word-level timing storage: JSON column, not a row-per-word table
- [0022](0022-alignment-algorithm.md) — Deterministic word-overlap alignment algorithm
- [0023](0023-provider-vs-platform-readiness.md) — Provider readiness is separate from platform readiness
- [0024](0024-llm-provider-selection.md) — LLM provider and extraction model selection
- [0025](0025-extraction-schema-design.md) — Extraction category/schema design
- [0026](0026-contradiction-detection.md) — Contradiction detection approach
- [0027](0027-synchronous-document-composition.md) — Document composition runs synchronously, not via ProcessingJob
- [0028](0028-dynamic-template-extraction-schemas.md) — Template-defined extraction categories build Pydantic schemas dynamically
- [0029](0029-remove-bundled-ollama.md) — Remove the bundled Ollama Compose service (GA-blocker fix, amends 0024)
