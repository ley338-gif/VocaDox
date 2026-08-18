# 0017 — Diarization provider and model selection

## Status
Accepted

## Context
Phase 3 needs one real, local speaker-diarization provider producing
speaker-attributed time turns. `pyannote.audio` was the presumptive
candidate per the brief, but the brief explicitly warns not to assume it
passes the license policy automatically — library and every model weight
were audited separately.

## Decision
**pyannote.audio** (library, pinned `>=4.0,<5.0` — see "Version pin
revised" below) + **`pyannote/speaker-diarization-3.1`** pipeline (which
itself composes `pyannote/segmentation-3.0`), pinned to Hugging Face
revision `84fd25912480287da0247647c3d2b4853cb3ee5` — verified 2026-08-18.

| Item | License | Source | Gated? | Commercial use | Redistribution |
|---|---|---|---|---|---|
| `pyannote.audio` library | MIT (verified: `LICENSE` file at `raw.githubusercontent.com/pyannote/pyannote-audio/develop/LICENSE`, copyright CNRS 2020) | PyPI / GitHub | No | Yes | Yes |
| `pyannote/speaker-diarization-3.1` pipeline | MIT (verified: model card at `huggingface.co/pyannote/speaker-diarization-3.1`, "License: mit") | Hugging Face | **Yes** — requires accepting the model's terms + a Hugging Face account/token to download | Yes | Yes (MIT permits it), but VocaDox never bundles/redistributes the weights itself — see below |
| `pyannote/segmentation-3.0` (pipeline dependency) | MIT (verified: model card at `huggingface.co/pyannote/segmentation-3.0`) | Hugging Face | **Yes** — same gate | Yes | Yes |

The pipeline card explicitly states it "will always remain open-source"
under MIT while noting the maintainers separately sell premium/paid
pipelines — the free, MIT pipeline used here is a distinct artifact from
those paid offerings, not a bait-and-switch.

Because both model repos are gated (require a logged-in Hugging Face
account to have accepted their terms, plus a user access token to
download), VocaDox does not — and legally/operationally cannot — bundle
these weights into any image or repository. **The admin installs the
model explicitly**, supplying their own Hugging Face token, via
`python -m app.cli.install_models diarization-default --token <hf_token>`
(see ADR-0018 and `docs/admin/model-installation.md`). This is documented
as an explicit requirement, not hidden behind a silent auto-download.

## Version pin revised after real testing (3.x -> 4.x)
The library was initially pinned `>=3.1,<3.4` — lighter dependency
footprint, and the pipeline card only requires "3.1 or higher." That
decision was **overturned by actually building the worker image and
importing the package** (not just reading changelogs): pyannote.audio
3.x's `pyannote/audio/core/io.py` calls `torchaudio.AudioMetaData`, a type
that modern `torchaudio` releases (resolved by pip today under 3.x's own
open-ended `torchaudio>=2.2.0` constraint) have removed entirely —
`AttributeError: module 'torchaudio' has no attribute 'AudioMetaData'` at
import time, every time, with no workaround short of hand-pinning an old
`torchaudio` release whose own compatibility envelope with everything
else (torch, faster-whisper's `av`/`ctranslate2`, CPU wheel availability)
would need separate re-verification. This is a confirmed, documented
upstream issue (pyannote/pyannote-audio#1952) — not a local misconfiguration.
`pyannote.audio` 4.x fixed this by moving off the removed torchaudio API
onto `torchcodec` instead, so **4.x is what's actually pinned and what was
verified to import and run** in this phase's real-model validation (see
PHASE_3_VALIDATION_REPORT.md). The heavier dependency set this pulls in
(`lightning`, `opentelemetry-*`, `torchcodec`, `pyannoteai-sdk`) is a real
cost of this reversal, fully reflected in
`compliance/dependency-inventory-transitive.yml` (scope: worker) with
every new transitive package individually license-verified — not a
footnote.

## Notable transitive dependency: pyannoteai-sdk
`pyannote.audio` 4.x depends on `pyannoteai-sdk` — the official Python
client for pyannoteAI's **commercial, cloud-hosted** diarization API
(requires an API key to actually call). This looked concerning at first
glance (a "free" library pulling in a paid-product SDK), but on
inspection: it's MIT-licensed (verified via its own GitHub `LICENSE`
file), VocaDox never configures an API key or imports/calls it, and
`PyannoteDiarizationProvider` only ever calls
`pyannote.audio.Pipeline.from_pretrained(local_path)` — the fully local,
offline pipeline path. It ships in the image as inert, unused, permissively-
licensed code, not a hidden network dependency; recorded in
`compliance/dependency-inventory-transitive.yml` like any other
transitive package rather than silently omitted.

## Rejected / not selected
- Fully unassisted/streaming clustering approaches without a
  pretrained segmentation+embedding pipeline were not pursued — pyannote's
  pretrained pipeline gives materially better speaker-change accuracy for
  the effort available in this phase.
- Older pre-3.1 pyannote pipelines were not used: the 3.1 pipeline card
  itself recommends 3.1 as the current baseline and removed a problematic
  `onnxruntime` dependency present in earlier versions.
- pyannote.audio 3.1-3.3 (the library) was tried first and **rejected**
  after the empirical `AudioMetaData` failure above — not a hypothetical
  concern, a reproduced local failure.

## Consequences
- `FakeDiarizationProvider` remains the only provider used by the
  mandatory CI test suite; `PyannoteDiarizationProvider` is exercised in
  this phase's real-model validation only where a Hugging Face token was
  actually available (see PHASE_3_VALIDATION_REPORT.md — if no token was
  available in the validation sandbox, this is marked NOT VERIFIED
  honestly rather than claimed).
- `compliance/model-inventory.yml` records both gated model repos with
  `bundled_with_product: false` and `download_method: admin-initiated
  (Hugging Face, requires accepted terms + token)`.
- Overlapping speech, ambiguous turns, and per-turn confidence are handled
  per `app/providers/diarization.py`'s `DiarizationResult` contract (see
  ADR-0022 for how the alignment stage turns this into honest
  CONFIDENT/AMBIGUOUS/OVERLAP/UNASSIGNED flags rather than forced
  certainty).
