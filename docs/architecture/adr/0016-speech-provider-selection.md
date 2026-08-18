# 0016 — Speech-to-text provider and model selection

## Status
Accepted

## Context
Phase 3 needs one real, local, offline-capable speech-to-text provider.
Candidates evaluated: OpenAI Whisper (reference implementation),
faster-whisper (CTranslate2 reimplementation), NVIDIA Parakeet, NVIDIA
Nemotron Speech, whisper.cpp.

Evaluation criteria: German accuracy, multilingual capability, word
timestamps, segment timestamps, speed, CPU support, NVIDIA GPU support,
model size, VRAM requirement, runtime dependency license, model-weight
license, commercial use, redistribution, offline operation, maintenance
status, Python integration quality.

## Decision
**faster-whisper** (library) + **`Systran/faster-whisper-small`**
(model weights), pinned to Hugging Face revision
`536b0662742c02347bc0e980a01041f333bce12` — verified 2026-08-18.

| Criterion | faster-whisper + Systran small |
|---|---|
| German accuracy | Whisper's multilingual training set includes German; qualitatively reasonable on the synthetic German fixture (see PHASE_3_VALIDATION_REPORT.md) |
| Multilingual | Yes — same weights, `language=None` auto-detects |
| Word timestamps | Yes (`word_timestamps=True`) — required for the alignment algorithm (ADR-0022) |
| Segment timestamps | Yes |
| Speed | CTranslate2 backend is substantially faster than reference PyTorch Whisper on both CPU (int8) and GPU (float16) |
| CPU support | Yes, `compute_type="int8"` |
| NVIDIA GPU support | Yes, `compute_type="float16"` |
| Model size (small) | ~484 MB (FP16 CTranslate2 weights) |
| VRAM requirement | ~1-2 GB for `small` |
| Runtime dependency license | faster-whisper: MIT (verified live against `https://pypi.org/pypi/faster-whisper/json`, 2026-08-18) |
| Model-weight license | MIT (verified live against the model card at `https://huggingface.co/Systran/faster-whisper-small`, 2026-08-18) — an unmodified CTranslate2 conversion of OpenAI's own MIT-licensed Whisper weights (`ct2-transformers-converter --model openai/whisper-small ...`, per the model card) |
| Commercial use | Yes (MIT, both library and weights) |
| Redistribution | Yes (MIT) — not gated, no Hugging Face login required to download |
| Offline operation | Yes, once the model directory is installed (see ADR-0018) |
| Maintenance | Actively maintained (SYSTRAN/guillaumekln lineage), widely adopted |
| Python integration | Native Python package, clean synchronous API wrapped in `asyncio.to_thread` (see `app/providers/speech_to_text.py`) |

Rejected:
- **Reference OpenAI Whisper (PyTorch)**: same model-weight license, but
  meaningfully slower inference for the same accuracy — no advantage over
  faster-whisper for this use case.
- **NVIDIA Parakeet / Nemotron Speech**: primarily English-optimized at
  evaluation time; German/multilingual support and licensing terms for
  redistributable weights were less clearly documented than Whisper's for
  the effort available in this phase. Worth re-evaluating in a later
  phase if German-specific accuracy becomes a driving requirement.
- **whisper.cpp**: viable CPU-oriented alternative, but faster-whisper's
  existing GPU path and native Python integration (no separate C++
  build/binding layer) fit this phase's worker architecture better.

Size selection: `small` (not `tiny`/`base`) as the default balance of
accuracy vs. speed/VRAM for a first production default; `medium`/`large-v3`
remain available by installing a different `speech-model_dir_name` profile
without any code change (the model identifier is never hardcoded in
worker code — see `app/core/ai_providers.py`).

## Consequences
- No model weights are bundled in any VocaDox image or repository — see
  ADR-0018 (install-time download, not build-time bundling).
- `FakeSpeechProvider` remains the only provider used by the mandatory
  (GPU-independent) CI test suite; `FasterWhisperSpeechProvider` is
  exercised only in this phase's real-model validation (sandbox with an
  actual GPU) and is never imported by any test that must pass without a
  real model installed.
- Because the model card documents the exact conversion command from
  `openai/whisper-small`, the effective terms trace cleanly back to
  OpenAI's own Whisper `LICENSE` file (MIT) — this was verified
  independently rather than assumed from "faster-whisper the library is
  MIT."
