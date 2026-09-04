# `app/profiles/`

**Status: implemented (Phase 6, extending Phase 4's minimal `ModelProfile`
foundation).**

`ModelProfile`/`ModelProfileVersion` (spec §18) — a real, admin-manageable,
versioned entity. `ProcessingProfile`/`ProcessingProfileVersion` (spec §19)
— named, user-friendly presets ("General", "Meeting") bundling Speech +
Diarization provider config, Extraction Model, Template + Template
Version, Prompt + Prompt Version, Language, Retention Policy.
`app.profiles.resolver.resolve_effective_config` implements the spec §20
Configuration Hierarchy (SYSTEM DEFAULT -> PROCESSING PROFILE ->
CONVERSATION OVERRIDE) with per-field source explainability.

Speech/Diarization remain `Settings`-driven configuration, not a full
`SpeechProfile`/`DiarizationProfile` DB entity — that table is still Phase
7 (see `docs/architecture/model-management-foundation.md`).

See `docs/architecture/templates.md`, `PHASE_6_VALIDATION_REPORT.md`, and
`app.profiles.seed` for the seeded initial profiles.
