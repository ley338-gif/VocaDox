#!/usr/bin/env python3
"""Development-only orchestration script: runs FastMSS
(https://github.com/popcornell/FastMSS, GPL-3.0) three times -- once per
overlap level -- and converts its output into the on-disk layout
`backend/app/analytics/diarization_fixtures.py` expects. See
`tools/dev/fastmss/README.md` for the full setup/license context before
running this.

**Never run in CI. Never part of any Docker build. Not a runtime
dependency of any VocaDox service** -- this script only shells out to a
separately-cloned, separately-installed FastMSS checkout (never vendored
into this repository) via subprocess, the same way one might shell out to
`ffmpeg` -- and copies FastMSS's *output data files* (waveforms + RTTM
text), not its source, into a fixture directory. See
`compliance/exceptions.yml`'s FastMSS entry for the full recorded license
disposition.

Pure stdlib (subprocess, shutil, pathlib) -- deliberately no new dependency
for VocaDox itself; whatever FastMSS needs is installed into its own,
separate environment (`--fastmss-python`), never backend/.venv.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# boost_overlap_factor -- see FastMSS's own Hydra config for the exact
# semantics; these three values are a starting point, not calibrated
# against a target overlap percentage. Confirm actual realized overlap in
# the generated RTTM (report_overlap_ratio.py) before relying on them --
# see README.md's "Honest caveat on 'overlap level'".
DEFAULT_BOOST_OVERLAP_FACTOR = {"none": 0.0, "some": 1.0, "heavy": 3.0}


def run_fastmss_sim(
    *,
    fastmss_repo: Path,
    fastmss_python: Path,
    manifest_dir: Path,
    sim_output_dir: Path,
    n_meetings: int,
    duration: int,
    n_jobs: int,
    min_max_spk: str,
    boost_overlap_factor: float,
) -> None:
    """One `recipes/sim.py` invocation (Hydra CLI overrides -- see FastMSS's
    own README for the authoritative parameter list)."""
    cmd = [
        str(fastmss_python),
        "recipes/sim.py",
        f"output_dir={sim_output_dir}",
        f"manifest_dir={manifest_dir}",
        f"n_meetings={n_meetings}",
        f"duration={duration}",
        f"n_jobs={n_jobs}",
        f"min_max_spk={min_max_spk}",
        f"boost_overlap_factor={boost_overlap_factor}",
        "save_rttm=true",
    ]
    print(f"+ (cwd={fastmss_repo}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=fastmss_repo, check=True)


def convert_sim_output(sim_output_dir: Path, dest_level_dir: Path) -> int:
    """Pairs every `*.rttm` FastMSS wrote (anywhere under `sim_output_dir`
    -- its exact output layout is a FastMSS implementation detail this
    script deliberately doesn't hardcode) with a same-stem `.wav`, and
    copies both into `dest_level_dir/<stem>.{wav,rttm}`. Returns the number
    of fixture pairs copied; an RTTM with no matching wav is skipped with a
    warning, never a hard failure (a partial/misconfigured FastMSS run
    should degrade to "fewer fixtures produced", not crash this script)."""
    dest_level_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for rttm_path in sorted(sim_output_dir.rglob("*.rttm")):
        wav_path = rttm_path.with_suffix(".wav")
        if not wav_path.is_file():
            print(f"  ! skip {rttm_path.name}: no matching .wav", file=sys.stderr)
            continue
        shutil.copyfile(rttm_path, dest_level_dir / rttm_path.name)
        shutil.copyfile(wav_path, dest_level_dir / wav_path.name)
        copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastmss-repo", type=Path, required=True)
    parser.add_argument(
        "--fastmss-python",
        type=Path,
        required=True,
        help="Python interpreter of FastMSS's OWN venv (never backend/.venv)",
    )
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="VocaDox fixture root to write into"
    )
    parser.add_argument("--n-meetings", type=int, default=10)
    parser.add_argument("--duration", type=int, default=30, help="seconds per simulated meeting")
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--min-max-spk", default="[2,3]", help="FastMSS min_max_spk override")
    parser.add_argument(
        "--boost-overlap-factor-none", type=float, default=DEFAULT_BOOST_OVERLAP_FACTOR["none"]
    )
    parser.add_argument(
        "--boost-overlap-factor-some", type=float, default=DEFAULT_BOOST_OVERLAP_FACTOR["some"]
    )
    parser.add_argument(
        "--boost-overlap-factor-heavy", type=float, default=DEFAULT_BOOST_OVERLAP_FACTOR["heavy"]
    )
    args = parser.parse_args()

    boost_by_level = {
        "none": args.boost_overlap_factor_none,
        "some": args.boost_overlap_factor_some,
        "heavy": args.boost_overlap_factor_heavy,
    }

    with tempfile.TemporaryDirectory(prefix="fastmss_sim_") as tmp:
        tmp_root = Path(tmp)
        for overlap_level, boost_overlap_factor in boost_by_level.items():
            sim_output_dir = tmp_root / overlap_level
            print(f"=== generating '{overlap_level}' overlap level ===", file=sys.stderr)
            run_fastmss_sim(
                fastmss_repo=args.fastmss_repo,
                fastmss_python=args.fastmss_python,
                manifest_dir=args.manifest_dir,
                sim_output_dir=sim_output_dir,
                n_meetings=args.n_meetings,
                duration=args.duration,
                n_jobs=args.n_jobs,
                min_max_spk=args.min_max_spk,
                boost_overlap_factor=boost_overlap_factor,
            )
            dest = args.output_dir / overlap_level
            copied = convert_sim_output(sim_output_dir, dest)
            print(f"  -> {copied} fixture(s) written to {dest}", file=sys.stderr)

    print(
        f"\nDone. Point VOCADOX_DIARIZATION_FIXTURES_DIR at {args.output_dir} "
        "and run POST /admin/evaluation/diarization-accuracy against a real "
        "diarization provider (VOCADOX_DIARIZATION_PROVIDER=pyannote) to score it.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
