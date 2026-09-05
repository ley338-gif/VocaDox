# Offline installation — consolidated guide

This is the definitive, whole-application answer to "can VocaDox run
with no internet access at all, and if so what does that actually
require." It consolidates Phase 3.1's real, empirically-verified
AI-model offline story (`offline-model-installation.md`) with the rest
of the stack, which Phase 11 reviewed specifically for this document.

**Honesty about scope**: this is a documentation consolidation pass, not
a new isolation test. Phase 3.1 already performed the one test that
matters most (real `HF_HUB_OFFLINE=1` enforcement, verified during real
inference) and explicitly documented what it did *not* verify (a true
network-namespace-level disconnection test). This phase did not improve
on that evidence — it is repeated below by reference, not re-claimed as
new. Where this phase adds anything, it is: confirming no other part of
the stack (backend, database, backup/restore, retention cleanup) has any
runtime network dependency beyond the compose network itself.

## The two-phase model

1. **Install time** (needs internet, once): pull container images, `pip
   install`/`npm install` dependencies (already vendored into the built
   images — a running deployment does not re-run these), and download AI
   model weights.
2. **Runtime** (after install, needs no internet at all): every
   container in `deploy/docker-compose.yml` communicates only with other
   containers on the compose network (`postgres`, `valkey`) or, for the
   `frontend`/`backend` services, with browsers/clients reaching them
   over whatever network the operator exposes — none of them make
   outbound internet calls during normal operation.

## Component-by-component runtime network survey

| Component | Runtime network calls? | Why / how enforced |
|---|---|---|
| `backend` (api) | None outbound. Serves inbound HTTP only. | No code path in `app/` makes an outbound HTTP/network call except to `postgres`/`valkey` (both compose-internal) — confirmed by inspection of every provider/service module; the app never calls an LLM/speech/diarization provider directly (that's the workers' job, and even the workers are offline — see below). |
| `worker-speech` / `worker-diarization` | None, once models are installed. | `app/workers/_offline_env.py` forces `HF_HUB_OFFLINE=1` before `huggingface_hub` can be imported — see `offline-model-installation.md` for the real test that found and fixed a hidden dependent-repo network call. `FasterWhisperSpeechProvider` never had a Hub-resolution step to begin with (loads model files directly off disk). |
| `worker-extraction` | Depends entirely on which LLM provider is configured. | If configured against a local Ollama instance (an admin-managed instance reachable via `VOCADOX_LLM_BASE_URL` — no longer a bundled compose service as of the Phase 12 GA-blocker fix, see `docs/architecture/adr/0029-remove-bundled-ollama.md`) that is itself running fully offline, no internet call from `worker-extraction`'s own network path. If configured against a real hosted LLM API, that is an explicit, visible outbound call by design (`VOCADOX_LLM_PROVIDER`/related settings) — not something this phase changes or hides. An offline deployment must use a local LLM provider, and that provider's own reachability (network location, offline-ness) is now the deploying admin's responsibility rather than something VocaDox's own compose stack guarantees. |
| `postgres` / `valkey` | None outbound (accept inbound compose-internal connections only). | Official images, no outbound calls in normal operation. |
| `frontend` | None outbound from the container itself; the browser loads the SPA and calls `backend` over whatever network path the operator exposes. | Static asset build (production `runtime` target) — no server-side rendering, no build-time-only dependency resolution at runtime. |
| Backup/Restore (`app.operations.backup_service`, Phase 11) | None outbound. | `pg_dump`/`pg_restore`/tar operate entirely against the compose-internal `postgres` service and local/mounted filesystem paths — no network calls beyond that. |
| Retention Cleanup (`app.operations.retention_service`, Phase 11) | None outbound. | Operates entirely against `postgres` (compose-internal) and the local/mounted media storage filesystem via `StorageProvider`. |

## What you need to actually run fully offline

1. **Pre-pull/pre-build every image** your compose profile uses while
   you still have internet access (`docker compose build`, `docker
   compose pull`), or transfer pre-built images via `docker save`/`docker
   load` into an air-gapped environment.
2. **Pre-install AI models** while you still have internet access and a
   Hugging Face token with the required repo access (see
   `offline-model-installation.md` and `docs/admin/model-installation.md`
   for exactly which repos), so the `vocadox_models_data` volume is
   already populated before the workers ever start in the offline
   environment.
3. **Stand up and configure your own local LLM provider** (e.g. an
   admin-managed Ollama instance you run yourself, capable of running
   fully offline once its own model is pulled — VocaDox does not bundle
   this any more, see `docs/admin/llm-provider.md`) if
   `worker-extraction`'s document-generation step needs to run offline
   too — a hosted LLM API is an explicit exception to "fully offline,"
   not a bug.
4. **No additional step is needed for backup/restore or retention
   cleanup** — both are pure database/filesystem operations with no
   external dependency of their own.

## What was NOT independently re-verified in this phase

Same limitation Phase 3.1 already stated, not improved on here: a real
network-namespace-level isolation test (`docker network disconnect` or a
host firewall egress rule, then confirming the full pipeline — capture,
transcribe, diarize, extract, compose, backup — still works) was not
performed. If a hard, verified network-isolation guarantee is a
requirement for your deployment, perform that test yourself using the
command sketch in `offline-model-installation.md`'s "What was NOT
independently verified" section, extended to include the `backend`
container and a `docker compose run --rm backup create` invocation.
