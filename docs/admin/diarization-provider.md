# Diarization provider (admin)

## What's configured

VocaDox's Phase 3 default diarization provider is **pyannote.audio**
(4.x) with the **pyannote/speaker-diarization-3.1** pipeline — see
`docs/architecture/adr/0017-diarization-provider-selection.md` for the
full evaluation, including a real compatibility issue found and fixed
during this phase's implementation (3.x's library couldn't actually load
against modern `torchaudio` — 4.x was substituted after that was
discovered by testing, not assumed).

| Setting | Env var | Default |
|---|---|---|
| Provider | `VOCADOX_DIARIZATION_PROVIDER` | `fake` |
| Device | `VOCADOX_DIARIZATION_DEVICE` | `auto` |
| Hugging Face token (install-time only) | `VOCADOX_HUGGINGFACE_TOKEN` | unset |

## Why this model requires extra setup

Unlike the speech model, `pyannote/speaker-diarization-3.1` is **gated**
on Hugging Face — even though its license is MIT, the maintainers require
you to log in, accept their terms, and generate a personal access token
before you can download it. VocaDox never bundles or silently downloads
this model on your behalf: it's a deliberate legal/operational boundary
(see `docs/security/model-supply-chain.md`).

The pipeline is also not a single download: its `config.yaml` names two
further Hugging Face repos by id, which `pyannote.audio` resolves
internally at pipeline-load time —
`pyannote/segmentation-3.0` (MIT, also gated, its own separate terms) and
`pyannote/wespeaker-voxceleb-resnet34-LM` (CC-BY-4.0, not gated). This
was discovered by real testing during Phase 3.1 (installing only the
top-level pipeline and then running real diarization inference produced
a live, unauthorized network call for `segmentation-3.0` at request
time) — see `compliance/model-inventory.yml` for all three entries and
`app/cli/install_models.py`'s `DependentRepo` for how they're installed
together.

To install it:
1. Create a (free) Hugging Face account if you don't have one.
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` and
   `https://huggingface.co/pyannote/segmentation-3.0`, and accept each
   model's terms while logged in (`wespeaker-voxceleb-resnet34-LM` is not
   gated — no acceptance step needed for it).
3. Generate a personal access token (Settings → Access Tokens).
4. Run `docker compose run --rm -e VOCADOX_HUGGINGFACE_TOKEN=<token>
   model-manager install diarization-default` — this downloads all three
   repos in one command. See `docs/admin/model-installation.md`.

## Checking status

`GET /api/v1/admin/providers/diarization` (requires `provider:read`)
mirrors the speech endpoint — `installed: false` until step 4 above
completes successfully.

## Speaker count hints

The provider accepts optional `min_speakers`/`max_speakers` hints per
processing request (not a global default — never assume every
conversation has, say, exactly 2 speakers). Leave them unset unless you
know the expected participant count in advance.

## Known limitations

- Diarization confidence is not currently a per-turn calibrated score
  from this pipeline (pyannote's default pipeline doesn't expose one) —
  VocaDox records an honest placeholder rather than a fabricated value;
  see `app/providers/diarization.py`.
- Overlapping speech is detected and flagged, not silently resolved.
