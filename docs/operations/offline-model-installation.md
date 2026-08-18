# Offline model installation and runtime

## Two distinct network requirements

VocaDox Phase 3 deliberately separates two different questions:

1. **Install-time network need**: yes, real. Downloading model weights
   from Hugging Face requires internet access (and, for the diarization
   model, an authenticated, terms-accepted Hugging Face session — see
   `docs/admin/model-installation.md`).
2. **Runtime network need after install**: intended to be none. Once
   models are present in the `vocadox_models_data` volume, the worker
   processes should never need to reach the internet to process a
   conversation.

## What was verified in this phase

- `FasterWhisperSpeechProvider`/`PyannoteDiarizationProvider` load models
  from a local directory path (`Settings.model_volume_root/<profile>`)
  via `WhisperModel(str(path), ...)` / `Pipeline.from_pretrained(str(path))`
  — neither call includes a Hugging Face repo ID or network parameter once
  a local path is given, which is the standard way both libraries avoid a
  network call for an already-downloaded local model.
- Code-level review confirms no other network call exists on the
  request-processing path (`app/processing/orchestrator.py`'s
  `execute_transcribe`/`execute_diarize`) outside of the explicit,
  separate `install_models.py` script.

## What was NOT independently verified

An actual "disconnect the network, then process a real conversation
end-to-end" test was not performed in this phase's sandbox (see
PHASE_3_VALIDATION_REPORT.md, Offline Test — marked NOT VERIFIED if that
test wasn't run, or PASS with the exact method if it was). Don't treat
the code-level analysis above as equivalent to that stronger, empirical
test — if fully offline operation is a hard requirement for your
deployment, perform that test yourself before relying on it in
production (block outbound network at the container/network level, then
run a transcription end-to-end).

## Recommended verification procedure

```sh
# After models are installed and providers are set to real:
docker network disconnect deploy_default vocadox-worker-speech-1
docker network disconnect deploy_default vocadox-worker-diarization-1
# (workers still need to reach postgres/valkey over the compose network —
# a full "no network at all" test additionally requires blocking egress
# to the internet specifically, e.g. via a host firewall rule, rather than
# disconnecting the compose network entirely.)
# Trigger processing via the API and confirm it completes successfully.
```
