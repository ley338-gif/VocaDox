# 0024 — LLM provider and extraction model selection

## Status
Accepted

## Context
Phase 4 needs one real, local LLM inference provider for structured fact
extraction (spec: local-first — conversation content must never leave the
deployment via a hosted/cloud API). The brief named Ollama, vLLM,
llama.cpp, and an OpenAI-compatible local endpoint as candidates to
evaluate, with Qwen named as an initial *model* candidate to evaluate, not
a mandate — same "verify, don't assume" posture Phase 3 applied to
faster-whisper/pyannote.

## Runtime evaluation

| Runtime | Structured/JSON-mode output | License | Notes |
|---|---|---|---|
| **Ollama** | Yes — `format` request field accepts a JSON Schema directly (`/api/generate`), verified with a real request (see below) | MIT (verified: `raw.githubusercontent.com/ollama/ollama/main/LICENSE`, 2026-09-03) | Simple HTTP server, trivial to run as one Compose service, wide model-format (GGUF) support, active project |
| vLLM | Yes (OpenAI-compatible `response_format`) | Apache-2.0 | Heavier to operate (Python-process-per-model, more complex GPU memory management); no clear advantage over Ollama at VocaDox's current single-model, single-GPU-host scale |
| llama.cpp (server) | Yes (`grammar`/`json_schema`) | MIT | Lower-level — Ollama itself is built on llama.cpp's inference core, so choosing Ollama gets the same inference engine with a friendlier model-management layer (pull/list/show) on top |

**Decision: Ollama**, run as its own Compose service (`ollama`), never
bundled model weights, never a cloud endpoint. `app.providers.llm
.OllamaLLMProvider` is a thin HTTP client — no `ollama` Python package
dependency needed, keeping the new pip footprint to just `httpx` (already
a dependency, see dependency-inventory.yml).

## Model evaluation

Candidates evaluated (all already available on the development
machine's local Ollama install, or pulled during this evaluation): a
Hermes-tuned Qwen3 variant, Qwen3:14b, Qwen2.5-coder:14b, Qwen2.5:14b.

| Criterion | Qwen2.5:14b (chosen) |
|---|---|
| Structured/JSON-schema output | Confirmed working with real requests against `format: <json schema>` — see PHASE_4_VALIDATION_REPORT.md's real-model validation transcript |
| Context length | 32,768 tokens (per Ollama model info) — ample for a single-conversation transcript at Phase 4's scale |
| German-language quality | Confirmed on a real synthetic German consultation transcript (Ramipril dosage example): correct extraction of German medical/scheduling facts, correct `NOT_MENTIONED` on genuinely absent info, no hallucinated values — see validation report |
| Resource requirements | ~9GB on disk (Q4_K_M quantization); real inference completed on the available local NVIDIA GPU within the configured timeout |
| Runtime license | N/A (weights, not runtime) — see model-inventory.yml |
| **Model-weight license** | **Apache-2.0** — verified from TWO independent primary sources: (1) `huggingface.co/Qwen/Qwen2.5-14B-Instruct/blob/main/LICENSE` (header "License: apache-2.0"), fetched 2026-09-03; (2) the actual GGUF blob pulled via `ollama pull qwen2.5:14b` embeds the identical Apache-2.0 text (`GET /api/show`'s `license` field) — the specific bytes running in this deployment were checked, not just the upstream model card |

Qwen3:14b/qwen3-hermes were not selected for Phase 4's default profile:
Qwen2.5:14b already met every requirement (structured output, context
length, German quality, clean Apache-2.0 license) with no need to
introduce a "thinking" model's extra latency/verbosity for a
narrow-schema extraction task. Nothing prevents a later `ModelProfile` row
pointing at a different pulled model — see `app.profiles`.

## Consequences
- `Settings.llm_provider` defaults to `"fake"` — a fresh checkout never
  silently requires a GPU/Ollama install to pass tests or start the app
  (same posture as `speech_provider`/`diarization_provider`).
- `app.profiles.ModelProfile` (not a hardcoded string in worker code)
  carries the actual model identifier — see ADR discussion in
  `docs/architecture/intelligence-pipeline.md`.
- The `ollama` container image itself (not the model) currently ships
  with one open, documented CRITICAL vulnerability finding baked into its
  upstream Go binary — see `compliance/container-inventory.yml`'s
  `ollama/ollama` entry and PHASE_4_VALIDATION_REPORT.md's Open Risks.
  This is a genuine, currently-unresolved gap requiring the product
  owner's decision, not silently waived.
