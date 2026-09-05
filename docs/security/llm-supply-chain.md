# LLM supply-chain security

Mirrors `docs/security/model-supply-chain.md`'s posture for Phase 3's
speech/diarization models, extended to Phase 4's LLM runtime and model.

## No silent network access

`worker-extraction` never downloads a model itself. Pulling a model into
the admin's own Ollama instance is an explicit admin action
(`ollama pull <tag>`, run directly against that instance — VocaDox does
not bundle an `ollama` Compose service, see
`docs/admin/llm-provider.md`) — there is no API endpoint or code path that
triggers an LLM model download at request time. `VOCADOX_LLM_PROVIDER`
defaults to `fake`, so a fresh install never silently reaches out to pull
a multi-gigabyte model, and `VOCADOX_LLM_BASE_URL` has no default at all
(see `docs/architecture/adr/0029-remove-bundled-ollama.md`), so there is
no well-known host it could silently reach out to even if misconfigured.

## Local-only inference — no cloud/hosted LLM API

`OllamaLLMProvider` sends every prompt (which includes real transcript
content) only to `Settings.llm_base_url` — a local or operator-controlled
Ollama instance, never a third-party hosted API (no OpenAI/Anthropic/etc.
client exists anywhere in this codebase). This is the direct
implementation of the spec's "local-first" LLM requirement: conversation
content never leaves the deployment via this path.

## Prompt/response content is never logged

`app.providers.llm.LLMProvider`'s docstring states the rule explicitly:
callers must never log the `prompt` argument or the returned `text`
verbatim — only opaque metadata (model name, token counts if available).
`app.processing.orchestrator.execute_extract`'s audit event
(`extraction.completed`) records only ids and counts
(`processing_run_id`, `facts_created`, `review_issues_created`), never
fact content or transcript text — see `docs/security/threat-model.md`'s
existing "never log full conversation content" rule, extended here.

## Model and runtime license verified separately

Per the standing rule in `compliance/model-inventory.yml`'s header: the
Ollama runtime's license (MIT) and the Qwen2.5-14B-Instruct model
weights' license (Apache-2.0) were verified from two independent primary
sources each, never assumed to match or inherited from general knowledge
— see `docs/architecture/adr/0024-llm-provider-selection.md`.

## No arbitrary model identifiers from user input

The extraction model identifier comes from a `model_profiles` database
row (`app.profiles.ModelProfile`), populated only by the seed script or a
future admin action — no API endpoint accepts an arbitrary Ollama model
tag from a caller and uses it for inference. A user cannot cause the
worker to pull or run an unvetted model.

## Structured-output constraint is not a security boundary

`complete_structured`'s JSON-Schema-constrained decoding
(`format: <schema>`) narrows the *shape* of the model's output to reduce
parsing failures — it is explicitly NOT treated as a trust boundary.
Every returned value is still validated against the Pydantic schema
(`app.intelligence.service._extract_category`), and every claimed
evidence segment is independently verified to exist in the real
transcript before being trusted (`app.intelligence.service
._resolve_evidence`) — the model's output is data to be checked, never
executed or trusted as-is. See ADR-0025.

## Resolved gap: container vulnerability scan finding (Phase 12 GA fix)

Earlier phases bundled an `ollama` Compose service (`ollama/ollama:0.33.2`)
whose container image carried one open CRITICAL Trivy finding
(CVE-2026-56854, an SSH-auth-bypass in a vendored Go crypto library that
VocaDox's own build process did not control). Rather than continue
carrying and re-accepting that finding, the Phase 12 GA-blocker fix
removed the bundled `ollama` Compose service entirely — VocaDox no longer
builds, ships, or scans that image at all. See
`docs/architecture/adr/0029-remove-bundled-ollama.md` for the full
decision record and PHASE_12_VALIDATION_REPORT.md for the re-validated
GA determination. VocaDox now always talks to an admin-managed external
Ollama instance (`docs/admin/llm-provider.md`), whose own container
supply chain is the deploying admin's responsibility, outside VocaDox's
build/scan scope.
