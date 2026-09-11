# 0048 — Sortformer: a second, real diarization provider

## Status

Accepted (2026-09-12), R1 (research roadmap, post-GA — second of R0-R3,
standing autonomous GO per `[[github-workflow-autonomy]]`).

## Context

R0 (ADR-0047) built a provider-agnostic DER/JER eval framework specifically
so a second diarization provider could be measured against `pyannote.audio`
using real metrics instead of another rubber-stamped synthetic fixture
(Phase 12 GA validation Finding #12). R0's own report named the concrete
next step: "R1 (Sortformer integration): can start on the provider
implementation immediately — no changes needed to `DiarizationProvider`."

The provider selected is NVIDIA's Streaming Sortformer 4-Speaker v2
(`nvidia/diar_streaming_sortformer_4spk-v2`), per the research letter that
scoped R1. Two questions had to be settled empirically before writing any
provider code, per this project's standing "verify before building"
discipline (ADR-0017's own pyannote 3.x->4.x reversal is the precedent):

1. Is the model's actual license what the research letter assumed (CC BY
   4.0), and is it really non-gated?
2. What does this model's real, documented usage pattern look like, so the
   implementation isn't invented from first principles?

## Decision

### License: CC BY 4.0, verified non-gated — via TWO independent sources

- The model card's own "License Information" section states: "License to
  use this model is covered by the CC-BY-4.0. By downloading the public and
  release version of the model, you accept the terms and conditions of the
  CC-BY-4.0 license" — permits commercial use and redistribution, with
  attribution to NVIDIA required.
- Independently verified against the Hugging Face model API directly
  (`GET https://huggingface.co/api/models/nvidia/diar_streaming_sortformer_4spk-v2`),
  2026-09-12: `"gated": false`, `"license": "cc-by-4.0"`, and `"sha":
  "5240a64075176943f677d30fa2171c780229f341"` (the exact commit pinned
  below).

**A real ambiguity worth recording, not silently resolved either way:** the
model card's own Python usage sample says "You need a Hugging Face token"
when calling `from_pretrained` directly against the HF repo id. Read
naively, this looks like ADR-0017's pyannote gate all over again. But the
HF API's own `gated` field for this exact repo returns `false` — the
token mention is HF's general authenticated-download convenience/rate-limit
guidance, not an actual terms-acceptance gate (unlike
`pyannote/speaker-diarization-3.1`, where the HF API genuinely reports
`gated: true` and a token is mandatory). `app/cli/install_models.py`'s
`diarization-sortformer` profile is registered with `requires_token=False`
accordingly — if this turns out wrong in practice (a real download attempt
without a token is rejected), that would be a license-policy-relevant
surprise requiring the owner's attention per this project's standing stop
conditions, not something to silently work around.

The runtime library, NVIDIA NeMo (`nemo_toolkit`, PyPI), is **Apache-2.0**
— verified via `raw.githubusercontent.com/NVIDIA/NeMo/main/LICENSE`
("Apache License Version 2.0, January 2004"), 2026-09-12. Both the model
weights and the runtime library license were verified SEPARATELY (never
assumed identical), matching this project's standing model-inventory
discipline.

### Single-file checkpoint, not a multi-repo pipeline

Unlike pyannote's `speaker-diarization-3.1` (a top-level pipeline that
resolves THREE separate Hugging Face repos internally, per ADR-0017's Phase
3.1 amendment), Sortformer ships as ONE self-contained `.nemo` archive
(`diar_streaming_sortformer_4spk-v2.nemo`) — verified directly against the
repo's own file listing (HF API `siblings`, 2026-09-12): `.gitattributes`,
`README.md`, the `.nemo` checkpoint, a `.gguf` quantization VocaDox does not
use, and demo GIFs. `app/cli/install_models.py`'s new
`diarization-sortformer` profile downloads only the `.nemo` file
(`allow_patterns`), no `dependent_repos` needed — a materially simpler
install than pyannote's.

`SortformerDiarizationProvider` (`app/providers/diarization.py`) therefore
loads the checkpoint via NeMo's own `.restore_from()` API — the standard
fully-offline single-file loader for any NeMo model — rather than
`from_pretrained(repo_id)`, which would resolve against Hugging Face at
call time. This preserves the same "never let a worker reach the network at
inference time" policy `PyannoteDiarizationProvider`/`_offline_env.py`
already enforce.

### Interface conformance: no changes needed to `DiarizationProvider`

Confirmed exactly as R0 predicted. `SortformerDiarizationProvider`
implements `diarize()`/`status()` like `PyannoteDiarizationProvider`:
normalizing the model's own `(begin_seconds, end_seconds, speaker_index)`
segment output (the model card's own documented output shape) into
`SpeakerTurn`/`DiarizationResult`. Two honest gaps versus pyannote, both
disclosed rather than papered over:

- **No per-turn confidence score** documented for this model's `diarize()`
  output — same `1.0` placeholder convention `PyannoteDiarizationProvider`
  already uses for the same reason (not a Sortformer-specific compromise).
- **No per-speaker voice-embedding extraction API** documented on this
  model card (unlike pyannote.audio 4.x's `DiarizeOutput.speaker_embeddings`,
  post-GA P1-2) — `speaker_embeddings` is always `None` for this provider.
  Voiceprint suggestion (ADR-0032) simply has no signal to offer when
  Sortformer is the configured provider; this degrades the same way it
  already does for any turn pyannote itself fails to extract an embedding
  for, never a hard failure.
- **min_speakers/max_speakers are accepted but unused**: this is a fixed
  4-speaker-max architecture with no documented speaker-count hint API,
  unlike pyannote's pipeline which genuinely uses these.

### Provider selection: `VOCADOX_DIARIZATION_PROVIDER=sortformer`

`app.core.ai_providers.get_diarization_provider` (the one factory function
domain code depends on — enforced by
`tests/test_architecture_boundaries.py`) now also accepts `"sortformer"`,
alongside the existing `"fake"`/`"pyannote"`. This is the same mechanism
R0's `run_diarization_accuracy_eval`/`POST /admin/evaluation/diarization-
accuracy` already depends on via FastAPI `Depends(get_diarization_provider)`
— switching the env var and re-running the Evaluation Lab's diarization-
accuracy endpoint is how an admin/developer compares pyannote vs. Sortformer
DER/JER on the same fixture set, one run per provider (R0's
`EvaluationRun.subject_b` remains a `{"note": "reserved for R1"}`
placeholder — R1 does not implement a single combined two-provider run;
see "Not done in R1" below).

A separate `diarization_sortformer_model_dir_name` setting (default
`diarization-sortformer`) keeps pyannote's and Sortformer's installed
checkpoints in different `model_volume_root` subdirectories, so an admin
can have both installed side by side — necessary to actually compare them
by switching the provider env var between two Evaluation Lab runs.

## Consequences

- `compliance/model-inventory.yml` records
  `nvidia/diar_streaming_sortformer_4spk-v2` with `bundled_with_product:
  false`, `commercial_use: true`, `redistribution: true` — a real
  model-inventory entry (not a `compliance/exceptions.yml` dev-tool
  exception like R0's FastMSS, since this ships in the product as a
  selectable production provider, not a dev-only test-fixture tool).
- `backend/pyproject.toml`'s `[ai]` extra grows by `nemo_toolkit[asr]`
  (Apache-2.0) and its own substantial transitive dependency tree
  (transformers, datasets, lightning, tensorboard, wandb, librosa, lhotse,
  and others — `uv lock` resolved 245 total packages for this extra,
  up from roughly 165 before this PR). This is a real, disclosed cost: the
  worker image (`backend/worker.Dockerfile`, which installs the `[ai]`
  extra for all three worker roles) grows materially. `uv lock` succeeded
  locally in this session (network access was available for dependency
  resolution) and pins CPU-only PyTorch wheels exactly like the existing
  `torch`/`torchaudio`/`torchcodec` entries (`[[tool.uv.index]]
  pytorch-cpu`) — no `nvidia-cublas`/`nvidia-cudnn` GPU binary packages
  appear in the resolved lock, confirming NeMo's own transitive deps
  (`cuda-bindings`, `cuda-pathfinder`) are lightweight Python bindings, not
  multi-GB CUDA runtime downloads.
- `compliance/dependency-inventory-transitive.yml` was **not** regenerated
  in this PR — `compliance/generate_transitive_inventory.py`'s own
  docstring requires running the raw pip-licenses scan on Linux (several
  resolved packages are platform-conditional between Windows and the
  ubuntu-latest CI runner CI's own compliance job builds against), and no
  Linux container was available in R1's development sandbox to produce a
  byte-identical scan. CI's compliance job regenerates this file for real
  on `ubuntu-latest` and fails on either drift or a genuinely
  blocked/unknown transitive license — R1 explicitly plans to let that run
  and fix whatever it surfaces with real, targeted follow-up commits
  (adding `PACKAGE_LICENSE_OVERRIDES` entries or, if warranted, a
  `compliance/exceptions.yml` entry), not to guess the full ~80-package
  license classification by hand from a non-Linux sandbox. See
  PHASE_R1_VALIDATION_REPORT.md for the outcome.
- `docs/admin/model-installation.md` gains the `diarization-sortformer`
  profile's install command alongside `diarization-default`.

## Not done in R1 (explicitly out of scope, per the task)

- **No single combined pyannote-vs-Sortformer comparison run.**
  `EvaluationRun.subject_b` stays a reserved placeholder; R1 makes it
  possible to run the *same* diarization-accuracy eval against either
  provider (switch the env var, run again, compare the two
  `EvaluationRun` rows by hand), not a single API call that runs both.
  Building a true side-by-side `subject_a`/`subject_b` comparison for
  diarization would be a reasonable R1.1/R2-adjacent follow-up, not
  something this ADR claims is done.
- **No real end-to-end inference verification.** See
  PHASE_R1_VALIDATION_REPORT.md for the full, honest account — no GPU, no
  `nemo_toolkit` install, and no real audio fixture were available in this
  session's sandbox to actually run `SortformerDiarizationProvider.diarize()`
  against real audio. The implementation follows the model card's
  documented usage pattern faithfully but is unverified end-to-end, exactly
  like `PyannoteDiarizationProvider` before Phase 3.1 closed that gap with a
  real token and a real install.
- R2 (second STT provider PoC), R3: untouched, per the task's explicit
  scope boundary.
