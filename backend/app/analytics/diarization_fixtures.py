"""R0 (research roadmap) diarization evaluation fixtures -- local-only,
provider-agnostic ground truth for the DER/JER eval framework
(`app.analytics.diarization_eval`).

Two distinct sources of fixtures, deliberately not conflated:

1. **Smoke fixtures** (`diarization_smoke_fixtures/`, committed to git): a
   handful of tiny (a few seconds), synthetically-generated two-tone audio
   files with hand-written RTTM ground truth, at three overlap levels
   (none/some/heavy). These exist ONLY to prove the eval framework's wiring
   (fixture loading -> provider.diarize() -> DER/JER -> Evaluation Lab
   record) end-to-end in mandatory CI, where only `FakeDiarizationProvider`
   is available (no GPU, no `ai` extra installed -- see
   `.github/workflows/ci.yml`'s `backend` job). They are NOT a substitute
   for real multi-voice empirical validation -- two sine tones are not
   speech, and `FakeDiarizationProvider` never even reads the audio file.
   See `PHASE_R0_VALIDATION_REPORT.md`, "Known Limitations".

2. **FastMSS-generated fixtures** (real, genuinely-distinct-human-voice
   audio composited from a real speech corpus, e.g. LibriSpeech, via
   FastMSS's HMM turn-taking simulator) -- generated locally by a developer
   with `tools/dev/fastmss/generate_fixtures.py` (never in CI, never
   downloaded/run automatically -- see that script's own docstring and
   `compliance/exceptions.yml`'s FastMSS entry for why). Point
   `VOCADOX_DIARIZATION_FIXTURES_DIR` at that output directory to make
   `discover_fixtures` pick them up instead of/in addition to the smoke set.

Both sources share the same on-disk shape so `discover_fixtures` handles
either: `<root>/<overlap_level>/<fixture_id>.wav` + `<fixture_id>.rttm`.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from app.analytics.diarization_metrics import DiarizationTurn
from app.analytics.rttm import parse_rttm

OVERLAP_LEVELS = ("none", "some", "heavy")


@dataclass(frozen=True, slots=True)
class DiarizationFixture:
    fixture_id: str
    overlap_level: str
    audio_path: str
    reference_turns: list[DiarizationTurn]
    duration_seconds: float
    source: str  # "smoke" | "fastmss" | other free-text provenance label


def _wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        return frames / float(rate) if rate else 0.0


def discover_fixtures(root: Path, *, source: str) -> list[DiarizationFixture]:
    """Scans `<root>/<overlap_level>/*.rttm` for each of `OVERLAP_LEVELS`,
    pairing each `<fixture_id>.rttm` with a same-named `.wav`. Skips (does
    not raise on) an RTTM file with no matching audio file, since a
    partially-generated fixture directory (e.g. FastMSS still running)
    should degrade to "fewer fixtures found", never a hard crash of the
    Evaluation Lab endpoint."""
    fixtures: list[DiarizationFixture] = []
    for overlap_level in OVERLAP_LEVELS:
        level_dir = root / overlap_level
        if not level_dir.is_dir():
            continue
        for rttm_path in sorted(level_dir.glob("*.rttm")):
            audio_path = rttm_path.with_suffix(".wav")
            if not audio_path.is_file():
                continue
            reference_turns = parse_rttm(rttm_path.read_text(encoding="utf-8"))
            try:
                duration = _wav_duration_seconds(audio_path)
            except (wave.Error, OSError):
                duration = max((t.end_seconds for t in reference_turns), default=0.0)
            fixtures.append(
                DiarizationFixture(
                    fixture_id=rttm_path.stem,
                    overlap_level=overlap_level,
                    audio_path=str(audio_path),
                    reference_turns=reference_turns,
                    duration_seconds=duration,
                    source=source,
                )
            )
    return fixtures


def smoke_fixtures_dir() -> Path:
    return Path(__file__).parent / "diarization_smoke_fixtures"


def load_smoke_fixtures() -> list[DiarizationFixture]:
    return discover_fixtures(smoke_fixtures_dir(), source="smoke")
