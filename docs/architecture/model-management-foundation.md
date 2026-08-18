# Model management (Phase 3 foundation only)

Phase 3 deliberately implements only the **backend/domain foundation**
for model management — a full admin Model Management UI (browse
available models, install/upgrade/remove from the browser, configure
provider profiles per-organization) is explicitly Phase 7 scope, not
this phase's.

## What exists today

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

## What's explicitly deferred to Phase 7

- A `SpeechProfile`/`DiarizationProfile` **database table** letting an
  admin define/select multiple named provider configurations from the UI.
- Installing/removing models from the admin UI itself (today: CLI only).
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
future Phase 7 admin UI can change which installed profile is active
without a code change, purely by changing configuration (and, later, a
database row).
