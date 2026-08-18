# Installing AI models

Models are **never** bundled into VocaDox's Docker images or downloaded
automatically at runtime (see
`docs/architecture/adr/0018-model-installation-strategy.md`). An admin
installs them explicitly, once, into a persistent volume.

## Prerequisites

- The `worker-speech`/`worker-diarization` containers must be built and
  runnable (`docker compose build worker-speech worker-diarization`).
- Internet access is needed for this install step only — not at runtime
  afterward (see `docs/operations/offline-model-installation.md`).
- For the diarization model: a Hugging Face account that has accepted the
  gated model's terms, and a personal access token (see
  `docs/admin/diarization-provider.md`).

## Installing the speech model

```sh
docker compose -f deploy/docker-compose.yml run --rm worker-speech \
  python -m app.cli.install_models speech-default
```

This downloads `Systran/faster-whisper-small` at its pinned revision into
`vocadox_models_data:/app/data/models/speech-default`. Re-running this
command is safe and fast — it detects the model is already installed and
skips re-downloading.

## Installing the diarization model

```sh
docker compose -f deploy/docker-compose.yml run --rm \
  -e VOCADOX_HUGGINGFACE_TOKEN=<your-hf-token> \
  worker-diarization python -m app.cli.install_models diarization-default
```

Without a token (and without having accepted the model's terms on
Hugging Face first), this fails with a clear error rather than a
confusing download failure partway through.

## Verifying the install

```sh
docker compose -f deploy/docker-compose.yml run --rm worker-speech \
  python -m app.cli.install_models --list
```

Or check `GET /api/v1/admin/providers/speech` / `.../diarization` after
setting `VOCADOX_SPEECH_PROVIDER=faster_whisper` /
`VOCADOX_DIARIZATION_PROVIDER=pyannote` and restarting the workers —
`installed: true` confirms it landed correctly.

## Disk space / model volume

Models live in the `vocadox_models_data` named volume, separate from
conversation media (`vocadox_backend_data`). `docker compose down`
(without `-v`) preserves it; only `docker compose down -v` removes it,
requiring a re-install. Budget roughly 500MB for the default speech
profile and a few tens of MB for the diarization pipeline+segmentation
checkpoints (see `compliance/model-inventory.yml`'s `disk_size_mb`
fields — these are approximate, not exact).

## Upgrading a model

Installing a different pinned revision (edit
`app/cli/install_models.py`'s `PROFILES` dict, or add a new profile) and
re-running the install command creates a new subdirectory under the
model volume — it never overwrites a previously-installed profile
in-place. Switching `VOCADOX_SPEECH_MODEL_DIR_NAME` (or the diarization
equivalent) points the provider at the new profile.
