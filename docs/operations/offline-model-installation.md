# Offline model installation and runtime

## Two distinct network requirements

VocaDox deliberately separates two different questions:

1. **Install-time network need**: yes, real. Downloading model weights
   from Hugging Face requires internet access (and, for the diarization
   model, an authenticated, terms-accepted Hugging Face session covering
   **all three** repos it needs — see `docs/admin/model-installation.md`
   and `docs/admin/diarization-provider.md`).
2. **Runtime network need after install**: none — enforced, not just
   intended. Once models are present in the `vocadox_models_data` volume,
   `worker-speech`/`worker-diarization` never reach the internet to
   process a conversation.

## What Phase 3.1 found and fixed

Phase 3's code-level review of this claim ("neither provider's
transcribe/diarize call path includes a network parameter once a local
model path is given") was **wrong in one specific way**, found only by
actually running real diarization inference with real models installed:

`pyannote/speaker-diarization-3.1`'s `config.yaml` names two further
Hugging Face repos by id (`segmentation`, `embedding`), which
`pyannote.audio` resolves internally via `huggingface_hub` at
pipeline-load time — not from the top-level pipeline's own local
directory. With those two dependent repos not yet installed, a real
worker made a live `HEAD
https://huggingface.co/pyannote/segmentation-3.0/...` request at
diarization request time and failed with `401 Unauthorized` — genuine,
silent-by-default network access in what was supposed to be a fully
offline runtime path. Two fixes closed this:

1. `docker compose run --rm model-manager install diarization-default`
   now downloads all three repos (see
   `app/cli/install_models.py`'s `DependentRepo`), not just the top-level
   pipeline.
2. `app/workers/_offline_env.py`, imported as the literal first statement
   of `app/workers/runner.py`, sets `HF_HUB_OFFLINE=1` for the entire
   worker process before `huggingface_hub` (or anything that imports it)
   can be imported anywhere in that process. This was not optional
   diligence — an earlier version of this fix set the same env var
   immediately before the `Pipeline.from_pretrained()` call instead, and
   it was a **silent no-op**: `huggingface_hub.constants.HF_HUB_OFFLINE`
   is read from `os.environ` exactly once, at that module's own first
   import, and cached as a plain `bool` forever after in that process.
   Setting the env var later has no effect once the module has already
   been imported. With `HF_HUB_OFFLINE=1` forced from process start, a
   missing dependent model now fails with a clear
   `LocalEntryNotFoundError`-class message instead of a live network call
   (spec: "runtime workers must fail clearly if a required local model is
   missing rather than silently downloading it").

`FasterWhisperSpeechProvider` was not affected by this bug — it loads
model files directly off disk (`WhisperModel(str(path), ...)`) with no
Hugging Face Hub resolution step at request time, so there was no hidden
dependent-repo problem to find there.

## Empirical offline-runtime test performed in Phase 3.1

With both `speech-default` and `diarization-default` (all three repos)
installed for real using the actual Hugging Face token in `deploy/.env`:

1. `worker-speech`/`worker-diarization` were started with
   `VOCADOX_SPEECH_PROVIDER=faster_whisper`,
   `VOCADOX_DIARIZATION_PROVIDER=pyannote`.
2. Real transcription + real diarization were run end-to-end against the
   2-speaker synthetic fixture
   (`backend/tests/fixtures/audio/german_multispeaker_conversation.wav`)
   via the live HTTP API — see `PHASE_3_1_VALIDATION_REPORT.md`'s "Real
   pyannote validation" section for the exact result.
3. `HF_HUB_OFFLINE=1` was confirmed set inside the running worker
   containers (`docker compose exec worker-diarization env | grep
   HF_HUB_OFFLINE`) for the whole duration of the test — i.e. every model
   load during that test happened with huggingface_hub itself refusing to
   make network calls, not merely "no network calls happened to occur."

This is the offline-runtime guarantee this phase can actually stand
behind: **the worker process cannot reach Hugging Face at all**, by
construction, not just "didn't happen to reach it in this test run."

## What was NOT independently verified

A full network-namespace-level "physically disconnect the container from
the internet, then process" test (e.g. `docker network disconnect` or a
host firewall rule blocking all egress from the worker containers) was
**not** performed in this phase — the `HF_HUB_OFFLINE=1` verification
above is a stronger, code-enforced guarantee for the one dependency that
matters (huggingface_hub), but it does not prove no *other* library in
the dependency tree could ever attempt a network call under some
different code path. If a hard network-isolation guarantee is a
requirement for your deployment, perform that stronger test yourself
before relying on it in production:

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
