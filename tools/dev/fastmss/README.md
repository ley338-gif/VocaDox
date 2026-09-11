# FastMSS dev-tool integration (R0, research roadmap)

**Development-only. Never installed, imported, or shipped by any VocaDox
runtime service or container. Never run in CI.**

## What this is for

[FastMSS](https://github.com/popcornell/FastMSS) composites real,
genuinely-distinct single-speaker recordings from an existing speech
corpus (e.g. LibriSpeech, via a [lhotse](https://github.com/lhotse-speech/lhotse)
manifest) into simulated multi-speaker "meetings", using an HMM turn-taking
model (4 transition types: turn hold, turn switch, interruption,
backchannel) to control how much speakers overlap, and can emit RTTM
ground truth (`save_rttm=true`). This is the real fixture-generation half
of R0's diarization eval framework (`backend/app/analytics/diarization_eval.py`)
-- see that module's docstring and `PHASE_R0_VALIDATION_REPORT.md` for why
this specifically (not TTS, not the bundled synthetic two-tone smoke
fixtures) is the concrete thing that can close Phase 12 Finding #12
("genuine multi-voice diarization accuracy has never been empirically
verified anywhere in this project").

## License disposition (read before running)

FastMSS is **GPL-3.0**. See `compliance/exceptions.yml`'s `FastMSS` entry
for the full recorded exception. Summary: it is a standalone external
tool a *developer* clones and runs locally to generate test-fixture files
(audio + RTTM text); nothing from its source is vendored, imported,
statically linked, or copied into any VocaDox package, image, or
distributed artifact. VocaDox's own code in this directory only invokes it
as a subprocess (like calling any other external CLI, e.g. `ffmpeg`) and
converts its *output data* (waveform + RTTM ground truth -- not
GPL-encumbered "source" in any meaningful sense, any more than a document
a GPL word processor saved would be) into `backend/app/analytics/diarization_fixtures.py`'s
directory layout. Generated fixtures are used only as local, non-distributed
test data feeding `POST /admin/evaluation/diarization-accuracy`; they are
not bundled into any shipped container image the way, say,
`pyannote/speaker-diarization-3.1` is.

**Do not** vendor a copy of FastMSS's source into this repository, add it
to `backend/pyproject.toml` (any extra, including `ai`/`dev`), or run it as
part of `docker build`/`docker compose`/CI. Doing so would put this
repository's own distribution under a materially different analysis than
the one recorded in `compliance/exceptions.yml` and would require
re-review before merging.

## Setup (one-time, per developer machine)

FastMSS is not vendored or pinned by this repo -- clone and manage it
yourself, in its own environment:

```bash
git clone https://github.com/popcornell/FastMSS.git ~/fastmss   # any local path outside this repo
cd ~/fastmss
python -m venv .venv && source .venv/bin/activate   # separate venv -- do NOT install into backend/.venv
pip install -e .   # see FastMSS's own README for its exact current dependency set (lhotse, hydra-core, ...)
```

You also need a source speech corpus as a lhotse manifest -- FastMSS does
not include or download one itself. The smallest practical real option is
LibriSpeech `dev-clean` (distinct human speakers, permissively licensed
for research use):

```bash
lhotse download librispeech --dataset-parts dev-clean /path/to/corpus
lhotse recipe librispeech /path/to/corpus /path/to/manifests   # produces the CutSet manifest FastMSS's sim.py expects as manifest_dir
```

("German-ish" per the R0 task scope: LibriSpeech is English -- VocaDox has
no equivalent open German multi-speaker corpus readily available for this
dev-only tool today. The fixtures this produces are structurally identical
diarization test data (genuinely distinct human voices, real overlap
patterns); only the spoken language differs from production German
conversations. Document this as a disclosed limitation, not a silent
substitution, in any report that cites a FastMSS-based empirical result.)

## Generating a fixture batch

```bash
cd <vocadox-repo>/tools/dev/fastmss
python generate_fixtures.py \
    --fastmss-repo ~/fastmss \
    --fastmss-python ~/fastmss/.venv/bin/python \
    --manifest-dir /path/to/manifests \
    --output-dir /path/to/vocadox-diarization-fixtures \
    --n-meetings 10 \
    --duration 30
```

This runs FastMSS's `recipes/sim.py` three times (via Hydra CLI overrides
-- see FastMSS's own docs for the full parameter set), once per overlap
level, and converts each run's `.wav`/`.rttm` output pairs into
`backend/app/analytics/diarization_fixtures.py`'s expected layout:
`<output-dir>/<overlap_level>/<fixture_id>.{wav,rttm}`.

**Honest caveat on "overlap level"**: `none`/`some`/`heavy` here map to
`boost_overlap_factor=0.0/1.0/3.0` -- these specific values are a starting
point (this HMM parameter scales FastMSS's own interruption/backchannel
transition rates; it does not directly set a target overlap percentage).
Confirm actual realized overlap ratios in the generated RTTM files
(`tools/dev/fastmss/report_overlap_ratio.py`) and adjust
`--boost-overlap-factor-*` before treating a given batch as "three
genuinely distinct overlap levels" for a validation report -- see
`PHASE_R0_VALIDATION_REPORT.md`'s Known Limitations for the status of this
repo's own reference batch (not generated in this environment -- no
network access to download a speech corpus; this is a real, runnable
runbook for whoever runs it next, not something this session executed).

## Using the generated fixtures

Point the backend at the generated directory instead of the bundled
synthetic smoke set:

```bash
export VOCADOX_DIARIZATION_FIXTURES_DIR=/path/to/vocadox-diarization-fixtures
```

Then `POST /admin/evaluation/diarization-accuracy` (Evaluation Lab, or the
"Sprechererkennung (DER/JER)" tab in the Admin UI) scores the currently
configured `VOCADOX_DIARIZATION_PROVIDER` (set to `pyannote` -- requires a
locally-installed pyannote snapshot, see `docs/admin/model-installation.md`
-- FakeDiarizationProvider cannot produce a meaningful real-voice result)
against this real batch instead.
