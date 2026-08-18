# Installing AI models

Models are **never** bundled into VocaDox's Docker images or downloaded
automatically at runtime (see
`docs/architecture/adr/0018-model-installation-strategy.md`). An admin
installs them explicitly, once, into a persistent volume, using the
dedicated `model-manager` command (Phase 3.1) — no Docker
`ENTRYPOINT`/`command` knowledge required.

> **Phase 3.1 note**: earlier documentation for this page told admins to
> run `docker compose run --rm worker-diarization python -m
> app.cli.install_models ...`. That command never actually worked — it
> collided with `worker.Dockerfile`'s `ENTRYPOINT`
> (`python -m app.workers.runner`), which rejected the extra arguments
> with `error: the following arguments are required: --role`. The
> `model-manager` service below is the fix: a dedicated, administrator-
> facing entrypoint that exists for exactly this purpose. If you have an
> older bookmark/runbook using the `worker-diarization` form, replace it.

## Prerequisites

- The `model-manager` image must be built:
  `docker compose build model-manager` (or just run the install command
  below — `docker compose run` builds it automatically if missing).
- Internet access is needed for this install step only — not at runtime
  afterward (see `docs/operations/offline-model-installation.md` and
  "What actually gets downloaded" below).
- For the diarization model: a Hugging Face account, a personal access
  token, **and terms accepted on all three of the models it needs** (see
  "What actually gets downloaded" below and
  `docs/admin/diarization-provider.md`).

## Listing available profiles

```sh
docker compose run --rm model-manager list
```

## Installing the speech model

```sh
docker compose run --rm model-manager install speech-default
```

Downloads `Systran/faster-whisper-small` at its pinned revision into
`vocadox_models_data:/app/data/models/speech-default`. Re-running this
command is safe and fast — it detects the model is already installed and
skips re-downloading.

## Installing the diarization model

```sh
docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<your-hf-token> \
  model-manager install diarization-default
```

Without a token (and without having accepted every dependent model's
terms on Hugging Face first — see below), this fails with a clear error
rather than a confusing partial download.

**Never** put the token directly in a shell command you might paste into
a chat, ticket, or shared terminal history — export it into your shell
session first (`export VOCADOX_HUGGINGFACE_TOKEN=...` / the PowerShell
equivalent) and reference the variable, exactly as shown above. VocaDox
itself never logs, persists, or echoes this token anywhere (verified: the
install output shown to the operator's terminal names only the model
repos and license notes, never the token value).

### What actually gets downloaded

`pyannote/speaker-diarization-3.1` is not a single self-contained
download. Its `config.yaml` names two further Hugging Face repos by id,
which `pyannote.audio` resolves internally at pipeline-load time — found
by real testing during Phase 3.1, not by reading pyannote's docs (the
Phase 3 implementation only downloaded the first of these three):

| Repo | License | Gated? | Role |
|---|---|---|---|
| `pyannote/speaker-diarization-3.1` | MIT | Yes | Top-level pipeline |
| `pyannote/segmentation-3.0` | MIT | Yes (separate terms acceptance) | Segmentation sub-model |
| `pyannote/wespeaker-voxceleb-resnet34-LM` | CC-BY-4.0 | No | Speaker-embedding sub-model |

`docker compose run --rm ... model-manager install diarization-default`
downloads **all three** in one command — an admin never needs to install
them individually. Before running it, your Hugging Face account must
have accepted terms on **both** gated repos (`speaker-diarization-3.1`
*and* `segmentation-3.0`) — visit each repo's page while logged in and
accept, then generate/reuse a personal access token with read access.
Full details, including exactly where each model's license was verified:
`compliance/model-inventory.yml` and `docs/admin/diarization-provider.md`.

The top-level pipeline installs into
`vocadox_models_data:/app/data/models/diarization-default`; the two
dependent repos install into a separate, shared cache directory
(`vocadox_models_data:/app/data/models/hf-cache`) that
`PyannoteDiarizationProvider` points `pyannote.audio` at directly — see
`app/cli/install_models.py`'s `DependentRepo` and
`app/providers/diarization.py`.

## Verifying the install

```sh
docker compose run --rm model-manager list
```

This only lists known profiles and their license notes, not installed
status. To confirm a model is actually loadable by a real worker, check
`GET /api/v1/admin/providers/speech` / `.../diarization` — but note this
reflects the **api** service's own provider config, which is always
`fake` by design (the api never loads a real provider itself — see
`docs/architecture/adr/0020-worker-topology.md`). To confirm a worker
itself sees an installed model, set `VOCADOX_SPEECH_PROVIDER=faster_whisper`
/ `VOCADOX_DIARIZATION_PROVIDER=pyannote`, (re)start
`worker-speech`/`worker-diarization`, and either watch its logs for a
successful pipeline load on the first real job, or exec into it and
run `ls /app/data/models/<profile-name>`.

## Disk space / model volume

Models live in the `vocadox_models_data` named volume, separate from
conversation media (`vocadox_backend_data`). `docker compose down`
(without `-v`) preserves it; **`docker compose down -v` removes it,
requiring a full re-install of every model** — this is a real,
destructive action, not just a restart. Budget roughly:

- `speech-default`: ~480 MB (`model.bin` dominates)
- `diarization-default` + its two dependent repos (`hf-cache`): well
  under 50 MB combined — the pipeline's own directory is a few KB of
  config/cards; the actual weights live in the two dependent repos'
  cache entries.

(See `compliance/model-inventory.yml`'s `disk_size_mb` fields for the
per-model breakdown — approximate, not exact.)

## Upgrading a model

Installing a different pinned revision (edit
`app/cli/install_models.py`'s `PROFILES` dict, or add a new profile) and
re-running the install command creates a new subdirectory under the
model volume — it never overwrites a previously-installed profile
in-place. Switching `VOCADOX_SPEECH_MODEL_DIR_NAME` (or the diarization
equivalent) points the provider at the new profile.
