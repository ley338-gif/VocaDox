# LLM provider (admin)

## What's configured

VocaDox's Phase 4 default LLM provider is **Ollama** (local, MIT-licensed
inference server) with **qwen2.5:14b** (Apache-2.0) as the default
extraction model — see
`docs/architecture/adr/0024-llm-provider-selection.md` for the full
evaluation.

| Setting | Env var | Default |
|---|---|---|
| Provider | `VOCADOX_LLM_PROVIDER` | `fake` |
| Ollama base URL | `VOCADOX_LLM_BASE_URL` | `http://ollama:11434` |
| Model tag | `VOCADOX_LLM_MODEL` | `qwen2.5:14b` |
| Context length (recorded on the seeded ModelProfile) | `VOCADOX_LLM_CONTEXT_LENGTH` | `32768` |
| Max output tokens | `VOCADOX_LLM_MAX_TOKENS` | `2048` |

`fake` (never a real model) is the default so a fresh checkout/CI never
silently requires a GPU or a running Ollama server — same posture as
`speech_provider`/`diarization_provider`.

## Why fact extraction is configuration, not a hardcoded model string

The actual model used for an extraction run is read from a `model_profiles`
database row (`app.profiles.ModelProfile`, purpose=`extraction`), not
directly from `Settings` — the settings above only **seed** that row on
first bootstrap (`python -m app.identity.bootstrap_admin`, or directly via
`python -m app.profiles.seed`). Changing the model later is a data change
(update or replace the row), not a code deploy. This is a deliberately
minimal foundation for the full Phase 6 Processing Profiles system, not
that system itself — see `docs/architecture/future-considerations.md`.

## Bringing up Ollama

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:14b
```

The model is pulled into the `vocadox_ollama_data` named volume — like
`vocadox_models_data` for speech/diarization, this is **never**
re-downloaded on `docker compose restart`/`up`; only `docker compose down
-v` destroys it. Once pulled, flip the worker over to the real provider:

```bash
# deploy/.env
VOCADOX_LLM_PROVIDER=ollama
```
```bash
docker compose up -d worker-extraction
```

## GPU

Only the `ollama` container is a candidate for GPU access (uncomment its
`deploy.resources.reservations.devices` block in
`deploy/docker-compose.yml`, same NVIDIA Container Toolkit setup as
`docs/admin/gpu-setup.md`) — `worker-extraction` itself talks to `ollama`
over plain HTTP and needs no GPU device of its own. CPU-only inference
works but is slow for a 14B model; expect noticeably higher latency per
extraction run — no formal CPU throughput numbers are published here yet
(see Known Limitations, PHASE_4_VALIDATION_REPORT.md).

## Bring your own Ollama (no Compose service)

`VOCADOX_LLM_BASE_URL` can point at any reachable Ollama instance — e.g.
one already running on the host (`http://host.docker.internal:11434` from
inside Compose, or `http://localhost:11434` outside it) instead of the
bundled `ollama` Compose service. This is the documented mitigation if an
operator chooses not to run the `ollama` container at all (see the open
vulnerability finding in `compliance/container-inventory.yml`'s
`ollama/ollama` entry) — the `worker-extraction` service and
`OllamaLLMProvider` code are unchanged either way.

## Triggering extraction

Extraction is **never automatic** — a user with `fact:extract` permission
explicitly calls `POST /api/v1/conversations/{id}/process/extract` once a
conversation's transcript is `READY` (same explicit-trigger policy as
Phase 3's transcription/diarization). See
`docs/user/facts-and-evidence.md`.

## Provider status / troubleshooting

`OllamaLLMProvider.status()` reports whether the configured model is
actually present on the Ollama server (`GET /api/tags`), never a fake
"Healthy" if it isn't. A missing model surfaces to the worker as
`LLMModelUnavailableError`, classified `FailureClass.MODEL_UNAVAILABLE`
(no blind auto-retry — requires the admin action above).
