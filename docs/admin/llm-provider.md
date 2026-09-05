# LLM provider (admin)

## What's configured

VocaDox's fact-extraction LLM provider is **Ollama** (MIT-licensed
inference server) with **qwen2.5:14b** (Apache-2.0) as the default
extraction model — see
`docs/architecture/adr/0024-llm-provider-selection.md` for the full
provider/model evaluation.

VocaDox does **not** bundle an `ollama` container in
`deploy/docker-compose.yml`. Point it at your own **admin-managed,
external Ollama instance** instead — anywhere reachable from the
`worker-extraction` service (the same host, another host on your network,
or a container you run and manage yourself outside VocaDox's Compose
stack). This is a deliberate GA-blocker fix, not an oversight — see
"Why there's no bundled Ollama service" below.

| Setting | Env var | Default |
|---|---|---|
| Provider | `VOCADOX_LLM_PROVIDER` | `fake` |
| Ollama base URL | `VOCADOX_LLM_BASE_URL` | *(none — must be set explicitly)* |
| Model tag | `VOCADOX_LLM_MODEL` | `qwen2.5:14b` |
| Context length (recorded on the seeded ModelProfile) | `VOCADOX_LLM_CONTEXT_LENGTH` | `32768` |
| Max output tokens | `VOCADOX_LLM_MAX_TOKENS` | `2048` |

`fake` (never a real model) is the default so a fresh checkout/CI never
silently requires a GPU or a running Ollama server — same posture as
`speech_provider`/`diarization_provider`. Unlike those settings,
`VOCADOX_LLM_BASE_URL` has **no default at all**: if you set
`VOCADOX_LLM_PROVIDER=ollama` without also setting
`VOCADOX_LLM_BASE_URL`, `worker-extraction` fails clearly and immediately
at startup with `LLMModelUnavailableError` (classified
`FailureClass.MODEL_UNAVAILABLE`) rather than silently trying to reach a
host that doesn't exist and just timing out.

## Why there's no bundled Ollama service

Earlier phases shipped a bundled `ollama` Compose service. Its pinned
image (`ollama/ollama:0.33.2`) carried one CRITICAL vulnerability,
CVE-2026-56854 (an SSH-auth-bypass in a vendored Go crypto library), with
no fixed upstream release available at the time. That finding was
disclosed and accepted by the product owner in Phase 4 and re-confirmed
unfixed at every phase through Phase 12 — but Phase 12's GA merge gate
requires a finding to be genuinely **fixed**, not re-accepted, to ship,
and correctly returned a NO-GO on this one item alone.

Rather than continue re-accepting the same unfixed CRITICAL indefinitely,
the product owner chose to drop the bundled `ollama` Compose service
entirely for GA (see
`docs/architecture/adr/0029-remove-bundled-ollama.md`) — this genuinely
removes the vulnerable component from VocaDox's own shipped footprint
(it is never built, started, or scanned by this project any more),
trading away the one-command bundled-LLM convenience for a clean security
posture. Running your own external Ollama instance was already fully
supported before this change; it is now the only supported path.

## Setting up your own Ollama instance

Run Ollama however suits your environment — a bare-metal/host install, a
container you manage yourself (`docker run -d -p 11434:11434 -v
ollama:/root/.ollama ollama/ollama:<a version you track and patch
yourself>`), or a shared instance elsewhere on your network. VocaDox does
not care how it got there, only that it's reachable over plain HTTP and
has the configured model pulled:

```bash
ollama pull qwen2.5:14b
```

Then point VocaDox at it and switch the worker over to the real provider:

```bash
# deploy/.env
VOCADOX_LLM_PROVIDER=ollama
# From inside Compose, reach a host-run Ollama via:
VOCADOX_LLM_BASE_URL=http://host.docker.internal:11434
# ...or any other network-reachable address, e.g.:
# VOCADOX_LLM_BASE_URL=http://ollama.internal.example.com:11434
```
```bash
docker compose up -d worker-extraction
```

Conversation content is sent only to the `VOCADOX_LLM_BASE_URL` you
configure, never to any cloud/hosted endpoint — this local-first
inference requirement is unchanged by the removal of the bundled service;
only who operates the Ollama process changed (you, instead of VocaDox's
Compose stack).

## GPU

GPU allocation for your external Ollama instance is entirely up to how
you run it (NVIDIA Container Toolkit if you run it as a container — see
`docs/admin/gpu-setup.md` for the general pattern — or a native install
with your GPU drivers already configured). `worker-extraction` itself
talks to it over plain HTTP and needs no GPU device of its own. CPU-only
inference works but is slow for a 14B model; expect noticeably higher
latency per extraction run — no formal CPU throughput numbers are
published here yet (see Known Limitations, PHASE_4_VALIDATION_REPORT.md).

## Triggering extraction

Extraction is **never automatic** — a user with `fact:extract` permission
explicitly calls `POST /api/v1/conversations/{id}/process/extract` once a
conversation's transcript is `READY` (same explicit-trigger policy as
Phase 3's transcription/diarization). See
`docs/user/facts-and-evidence.md`.

## Provider status / troubleshooting

`OllamaLLMProvider.status()` reports whether the configured model is
actually present on the Ollama server (`GET /api/tags`), never a fake
"Healthy" if it isn't. A missing model, or an unreachable server, surfaces
to the worker as `LLMModelUnavailableError`, classified
`FailureClass.MODEL_UNAVAILABLE` (no blind auto-retry — requires the
admin action above). If `VOCADOX_LLM_PROVIDER=ollama` is set without
`VOCADOX_LLM_BASE_URL`, the same `LLMModelUnavailableError` is raised
immediately at provider-construction time (worker startup, or first
admin-API status call) with a message naming exactly what's missing.
