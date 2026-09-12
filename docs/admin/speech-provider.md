# Speech-to-text provider (admin)

## What's configured

VocaDox's Phase 3 default speech provider is **faster-whisper**
(CTranslate2-based Whisper inference) with the **Systran/faster-whisper-small**
model — see `docs/architecture/adr/0016-speech-provider-selection.md` for
the full evaluation and license audit.

Configuration is file/env-based in Phase 3 (no admin UI yet — that's
Phase 7's Model Management work):

| Setting | Env var | Default |
|---|---|---|
| Provider | `VOCADOX_SPEECH_PROVIDER` | `fake` (never real unless explicitly changed) |
| Device | `VOCADOX_SPEECH_DEVICE` | `auto` (GPU if available, else CPU) |
| Model volume root | `VOCADOX_MODEL_VOLUME_ROOT` | `/app/data/models` |

Set `VOCADOX_SPEECH_PROVIDER=faster_whisper` on the `worker-speech`
service (see `deploy/compose.dev.yml`) only **after** installing the
model (`docs/admin/model-installation.md`) — the provider status endpoint
will otherwise honestly report "not installed" rather than silently
falling back or crashing.

## Checking status

`GET /api/v1/admin/providers/speech` (requires the `provider:read`
permission) returns:

```json
{
  "provider": "faster-whisper",
  "model": "Systran/faster-whisper-small",
  "model_revision": "536b0662742c02347bc0e980a01041f333bce12",
  "installed": true,
  "device": "cuda",
  "cuda_available": true,
  "detail": null
}
```

`installed: false` means the model directory doesn't exist yet — run the
install step. This endpoint is separate from `/health/ready` (see
`docs/architecture/adr/0023-provider-vs-platform-readiness.md`): a
missing model never takes the whole platform down.

## Languages

`faster-whisper` supports automatic language detection and explicit
`de`/`en` hints (and others Whisper was trained on) — German is the
primary target language for this deployment; only DE/EN/AUTO have been
practically tested in this phase (see PHASE_3_VALIDATION_REPORT.md).
Don't assume untested languages will perform equivalently.

## Choosing a different model size

The model identifier is never hardcoded in worker code — change
`speech_model_dir_name`/install a different profile (e.g. `medium`,
`large-v3`) via `app/cli/install_models.py` if you need higher accuracy
at the cost of speed/VRAM. This isn't wired up as a ready-made CLI
profile yet beyond the default; treat this as an extension point.

## Second provider (R2, research roadmap, post-GA): NVIDIA Nemotron 3.5 ASR Streaming 0.6B

A second, real `SpeechToTextProvider` — NVIDIA NeMo's
`nvidia/nemotron-3.5-asr-streaming-0.6b` (OpenMDW-1.1, not gated) — was
added in R2, following the exact same shape R1 proved for diarization
(Sortformer). See
`docs/architecture/adr/0049-nemotron-second-stt-provider.md` and
`PHASE_R2_VALIDATION_REPORT.md` for the full research, including the
OpenMDW-1.1 license disposition (a license not previously used in this
project).

To use it:

1. Install the checkpoint: `docker compose run --rm model-manager install
   stt-nemotron` (no Hugging Face token required — not gated).
2. Set `VOCADOX_SPEECH_PROVIDER=nemotron` on the `worker-speech` service.

**PoC-scoped disclosure**: real NeMo ASR inference was never executed
against this implementation in R2's development sandbox (no GPU, no
`nemo_toolkit` install, no model download available there) — the
provider follows the model card's documented usage pattern faithfully
but is honestly unverified end-to-end. It also currently reports the
whole file as a single segment with no word-level timestamps/confidence
and an unknown (`0.0`) duration — the model card's simplest documented
`.transcribe()` usage sample does not document a richer output shape the
way faster-whisper's `segments`/`words` objects do. Nothing in this
project has yet run a real Word Error Rate comparison between
faster-whisper and Nemotron (see PHASE_R2_VALIDATION_REPORT.md's Known
Limitations) — this is a PoC second provider, not yet a validated
alternative to faster-whisper for production transcription.
