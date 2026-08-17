# AI model licenses

**Status: empty in Phase 0.** No AI models (speech-to-text, diarization, or
LLM weights) are bundled, downloaded, or referenced by this repository yet
— Phase 0 ships only provider *interfaces* plus deterministic fakes (see
`docs/architecture/adr/0005-provider-abstraction-fakes.md`). Real model
integrations (Whisper for STT, pyannote for diarization, an Ollama-served
LLM, ...) are Phase 3/4 work.

`compliance/model-inventory.yml` exists now with the schema this document
will summarize once populated: `name`, `version`, `source`, `license`,
`commercial_use`, `redistribution`, `usage_restrictions`, `sha256`,
`bundled`, `downloaded_at_install`, `approval_status` (per spec §12).

When the first real model is integrated, this document must be updated
alongside `compliance/model-inventory.yml` with the model's actual license
terms, verified against its real source (model card / official
repository), before that integration is considered complete — the same
"verify, don't assume" standard used for the software dependency and
container inventories.
