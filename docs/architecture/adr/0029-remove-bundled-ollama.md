# 0029 — Remove the bundled Ollama Compose service (GA-blocker fix)

## Status
Accepted (2026-09-05). Amends
[0024-llm-provider-selection](0024-llm-provider-selection.md).

## Context

[ADR-0024](0024-llm-provider-selection.md) chose Ollama as VocaDox's LLM
runtime for fact extraction and shipped it as a bundled `ollama` service
in `deploy/docker-compose.yml`, pinned to `ollama/ollama:0.33.2`. A Trivy
scan at the time found one CRITICAL vulnerability in that image,
**CVE-2026-56854** (an SSH-auth-bypass in `golang.org/x/crypto/ssh`, a Go
crypto library vendored into the Ollama binary). `ollama serve` never
starts an SSH server — it exposes only its HTTP REST API on `:11434` — so
the vulnerable code path was assessed as unreachable via any interface
VocaDox actually exposes. On the strength of that reachability analysis,
the product owner accepted the finding in Phase 4 (2026-08-18).

The finding was carried forward, re-verified, and re-accepted unchanged
at every subsequent phase through Phase 11. At each check, no upstream
fix existed: the Go ecosystem's fix for CVE-2026-56854
(golang/go#80213) remained unreleased ("FixPending"), and no newer
`ollama/ollama` tag was built against a patched `golang.org/x/crypto`.

Phase 12 (Hardening/RC), the project's final phase, re-ran the same scan
and reached the same technical conclusion — but Phase 12's own merge gate
is deliberately stricter than every prior phase's: a CRITICAL finding
must be **fixed**, not merely disclosed and re-accepted, to reach GA. The
finding was unchanged from Phase 4, so Phase 12 correctly returned a
**NO-GO for GA** — the accept-and-carry-forward pattern that worked for
intermediate phases is not sufficient for a final release determination.

`PHASE_12_VALIDATION_REPORT.md` laid out three ways to resolve this for
GA:

1. Keep re-accepting the risk and override Phase 12's gate for this one
   finding (does not genuinely fix anything — just documents the same gap
   a fourth time).
2. **Drop the bundled `ollama` Compose service and require an
   admin-managed external Ollama instance instead** — already fully
   supported via `VOCADOX_LLM_BASE_URL` (see the pre-existing "Bring your
   own Ollama" section this ADR's companion doc change replaces).
3. Wait for an upstream Ollama release built against a patched
   `golang.org/x/crypto` (timeline outside VocaDox's control).

## Decision

**Option 2.** The product owner chose to drop the bundled `ollama`
Compose service from `deploy/docker-compose.yml` entirely, removing the
vulnerable component from VocaDox's own shipped container footprint
rather than continuing to accept risk on it. VocaDox now always talks to
an Ollama instance the deploying admin runs and manages themselves,
anywhere reachable over HTTP from `worker-extraction`, configured via
`VOCADOX_LLM_BASE_URL` (see `docs/admin/llm-provider.md`). There is no
default for that setting any more — the previous default,
`http://ollama:11434`, pointed at a container that no longer exists, and
defaulting to it would just produce a connection timeout instead of a
clear error. `get_llm_provider`/`get_llm_provider_for_model_identifier`
(`backend/app/core/ai_providers.py`) now raise `LLMModelUnavailableError`
immediately if `VOCADOX_LLM_PROVIDER=ollama` is set without an explicit
`VOCADOX_LLM_BASE_URL` — the same "fail clearly, never silently
misbehave" policy already applied to a genuinely-missing speech/
diarization model.

Concretely, this change:
- Removes the `ollama` service and `vocadox_ollama_data` volume from
  `deploy/docker-compose.yml`.
- Removes the `ollama/ollama` entry from
  `compliance/container-inventory.yml` (it is no longer part of VocaDox's
  own shipped container set — nothing left to track or accept risk on).
- Changes `Settings.llm_base_url` (`backend/app/platform/config.py`) from
  a default of `"http://ollama:11434"` to no default (`None`).
- Makes the "Bring your own Ollama" path in
  `docs/admin/llm-provider.md` the primary and only documented setup —
  previously framed as an opt-in mitigation for the vulnerability, now
  simply how LLM provider configuration works.
- Removes `OLLAMA_PORT` and the bundled-service framing from
  `deploy/.env.example`.

The runtime choice (Ollama itself, MIT-licensed) and the model choice
(Qwen2.5:14b, Apache-2.0) from ADR-0024 are unchanged — only *who runs
the Ollama process* changes (the deploying admin, instead of VocaDox's
own Compose stack). `app.providers.llm.OllamaLLMProvider` is unmodified;
it was already a generic HTTP client against any Ollama base URL.

## Consequences

- **Genuinely fixes** the Phase 12 GA blocker: CVE-2026-56854 is no
  longer present in anything VocaDox builds, ships, or scans, because the
  image that carried it is no longer part of VocaDox's shipped footprint
  at all. This is a real fix, not another disclosure/acceptance cycle.
- **Lost**: the one-command bundled-LLM convenience
  (`docker compose up` no longer brings up a working local LLM out of the
  box). An admin must now separately stand up and manage their own Ollama
  instance before enabling real (non-`fake`) extraction. This was
  considered and accepted as the right trade for a clean GA security
  posture over developer/operator convenience.
- `docker compose up` with no LLM configuration continues to work exactly
  as before: `VOCADOX_LLM_PROVIDER` still defaults to `"fake"`, so a fresh
  checkout never requires any Ollama instance, bundled or external.
- Any existing deployment that relied on the bundled `ollama` service and
  its default `VOCADOX_LLM_BASE_URL=http://ollama:11434` must, on
  upgrading to this version, stand up its own Ollama instance and set
  `VOCADOX_LLM_BASE_URL` explicitly — `worker-extraction` will otherwise
  fail fast at startup with a clear `LLMModelUnavailableError` (by
  design) rather than silently degrade.
- `compliance/model-inventory.yml`'s Qwen2.5-14B-Instruct entry and
  `compliance/dependency-inventory.yml`'s httpx/Ollama note were updated
  to reflect the external-instance framing; no license/approval status
  changed for either.
