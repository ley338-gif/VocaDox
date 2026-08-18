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
**pyannote.audio** (library, pinned `>=3.1,<3.4`) +
**`pyannote/speaker-diarization-3.1`** pipeline (which itself composes
`pyannote/segmentation-3.0`), pinned to Hugging Face revision
`84fd25912480287da0247647c3d2b4853cb3ee5` — verified 2026-08-18.

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

## Rejected / not selected
- Fully unassisted/streaming clustering approaches without a
  pretrained segmentation+embedding pipeline were not pursued — pyannote's
  pretrained pipeline gives materially better speaker-change accuracy for
  the effort available in this phase.
- Older pre-3.1 pyannote pipelines were not used: the 3.1 pipeline card
  itself recommends 3.1 as the current baseline and removed a problematic
  `onnxruntime` dependency present in earlier versions.
- `pyannote.audio` 4.x (current PyPI latest, 4.0.7) was evaluated and
  **not** pinned — it pulls in a substantially heavier dependency set
  (`lightning`, `opentelemetry-*`, `torchcodec`) not needed for this
  phase's scope, and the `speaker-diarization-3.1` pipeline card itself
  only requires "`pyannote.audio` version 3.1 or higher," so `>=3.1,<3.4`
  is the more conservative, lighter-dependency choice.

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
