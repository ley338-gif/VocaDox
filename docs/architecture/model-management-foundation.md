# Model management (Phase 3 foundation; Phase 6 extended ModelProfile/ProcessingProfile; Phase 7 admin surface)

Phase 3 deliberately implemented only the **backend/domain foundation**
for model management. Phase 6 (see `docs/architecture/templates.md`) made
`ModelProfile` a real, versioned, admin-manageable entity and added the
`ProcessingProfile` system on top of it. Phase 7 added the Admin Portal
pages (`/admin/models`, `/admin/speech`, `/admin/diarization`,
`/admin/profiles`) that surface real provider status and let an admin set
`speech_provider_config`/`diarization_provider_config` per Processing
Profile version — but a full admin Model Management UI (browse available
models, install/upgrade/remove from the browser) and a real
`SpeechProfile`/`DiarizationProfile` **database** entity remain future
work, not this phase's — see "What's still deferred beyond Phase 7" below.

## What exists today (Phase 7)

- `/admin/models`, `/admin/speech`, `/admin/diarization` (`GET
  /admin/models`, gated `provider:read`) — real, live-checked provider
  status for speech/diarization/LLM in one place. No install/upgrade/
  remove action from the browser (see "deferred" below) — links to the
  CLI instead.
- `/admin/profiles`'s "New draft version" form sets
  `speech_provider_config`/`diarization_provider_config` on a new
  `ProcessingProfileVersion` — the first UI to edit these JSON hints
  (previously REST-API-only since Phase 6).

## What existed before Phase 7 (Phase 6)

- `ModelProfile`/`ModelProfileVersion` (spec §18) — a real, admin-manageable,
  versioned entity (`app.profiles.models`, `PATCH /api/v1/model-profiles/{id}`).
- `ProcessingProfile`/`ProcessingProfileVersion` (spec §19) — named,
  friendly presets ("General", "Meeting") bundling extraction model +
  template + language + retention. See `docs/architecture/templates.md`.
- The Configuration Hierarchy resolver (`app.profiles.resolver`, spec §20).

## What existed before Phase 6 (Phase 3 baseline, still true for Speech/Diarization)

- `SpeechProfile`/`DiarizationProfile` equivalent: `Settings.speech_provider`,
  `speech_model_dir_name`, `speech_device` (and the diarization
  equivalents) — file/env-based configuration, not a database-backed
  profile entity yet.
- `compliance/model-inventory.yml` — the license/provenance record for
  every model VocaDox knows how to install.
- `app/cli/install_models.py` — the explicit, admin-run install command
  (see `docs/admin/model-installation.md`).
- `GET /api/v1/admin/providers/speech` / `.../diarization` — read-only
  status (see `docs/architecture/adr/0023-provider-vs-platform-readiness.md`).

## What's still deferred beyond Phase 7

- A `SpeechProfile`/`DiarizationProfile` **database table** letting an
  admin define/select multiple named, reusable provider configurations
  from the UI — Phase 7 only added editing the existing small JSON hints
  per Processing Profile version, not this real entity.
- Installing/removing models from the admin UI itself (today: CLI only,
  `/admin/models` links to it rather than reimplementing it).
- Multi-model catalog browsing (today: two hardcoded profiles,
  `speech-default`/`diarization-default`, in `install_models.py`).
- Per-organization provider configuration (today: one global
  provider config for the whole deployment).
- Signed/attested model integrity verification beyond revision-pin +
  marker-file-presence (see ADR-0018's Known Limitation).

## Why the model identifier is never hardcoded in worker code

`app/core/ai_providers.py`'s `get_speech_provider`/`get_diarization_provider`
read the model directory name from `Settings`, not from a literal string
inside `FasterWhisperSpeechProvider`/`PyannoteDiarizationProvider` — so a
future admin UI can change which installed profile is active without a
code change, purely by changing configuration (and, later, a database
row, once the `SpeechProfile`/`DiarizationProfile` entity above exists).
