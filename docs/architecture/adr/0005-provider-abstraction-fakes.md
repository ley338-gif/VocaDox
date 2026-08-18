# 0005 — Provider abstraction + fake-provider strategy

## Status
Accepted

## Context
Speech-to-text, diarization, and LLM completion all depend on third-party
engines (Whisper, pyannote, Ollama, ...) that are heavyweight, sometimes
GPU-bound, and out of scope for Phase 0 (spec §69: real integrations land
Phase 3/4). Building and testing everything else (API contracts, pipeline
orchestration once it exists, UI against realistic data) shouldn't have to
wait on those integrations, and tests must never depend on GPU hardware or
network calls to third-party model services.

## Decision
Define abstract interfaces in `backend/app/providers/`:
`SpeechToTextProvider`, `DiarizationProvider`, `LLMProvider`, and
`StorageProvider`. Ship exactly one real implementation in Phase 0 —
`LocalFilesystemStorage` — because it's plain filesystem code with no
licensed third-party engine behind it. For the other three, ship only
deterministic `Fake*` implementations (`FakeSpeechProvider`,
`FakeDiarizationProvider`, `FakeLLMProvider`) that return fixed synthetic
data, used by tests and local development. Real engine integrations are
explicitly deferred and will each get their own ADR when implemented
(license review included — e.g. model weight licenses go through
`compliance/model-inventory.yml`).

## Consequences
- Application code (once domain logic exists) is written against the
  interface, never a concrete engine, so swapping/adding engines later
  doesn't ripple through call sites.
- CI and local dev never need GPU access or network calls to model
  providers to pass tests.
- The `FakeLLMProvider`'s `complete()` never echoes the input prompt
  verbatim in its response, reinforcing (in tests) the no-prompt-logging
  rule from spec §63.
