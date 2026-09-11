#!/usr/bin/env python3
"""Development-only helper: reports the actual realized overlap ratio
(fraction of total speech time where >=2 reference speakers are
simultaneously active) for every `.rttm` file under a directory --
used to confirm a FastMSS batch's `--boost-overlap-factor-*` choices
actually produced the intended none/some/heavy separation before trusting
it as R0's empirical fixture batch (see `tools/dev/fastmss/README.md`'s
"Honest caveat on 'overlap level'").

Standalone, pure stdlib (deliberately does not import from `backend/app`
-- this tool runs in its own environment, not backend/.venv, per
README.md's setup instructions).

Usage: python report_overlap_ratio.py <fixture_root_or_rttm_dir> [...]
"""

from __future__ import annotations

import sys
from pathlib import Path


def parse_rttm_turns(text: str) -> list[tuple[float, float, str]]:
    turns = []
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) < 8 or fields[0] != "SPEAKER":
            continue
        try:
            onset, duration = float(fields[3]), float(fields[4])
        except ValueError:
            continue
        if duration > 0:
            turns.append((onset, onset + duration, fields[7]))
    return turns


def overlap_ratio(turns: list[tuple[float, float, str]]) -> float:
    if not turns:
        return 0.0
    boundaries = sorted({t[0] for t in turns} | {t[1] for t in turns})
    total_speech = 0.0
    overlapping = 0.0
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        duration = end - start
        active = sum(1 for turn_start, turn_end, _ in turns if turn_start <= start and end <= turn_end)
        if active >= 1:
            total_speech += duration
        if active >= 2:
            overlapping += duration
    return (overlapping / total_speech) if total_speech > 0 else 0.0


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    for arg in sys.argv[1:]:
        root = Path(arg)
        rttm_files = sorted(root.rglob("*.rttm")) if root.is_dir() else [root]
        if not rttm_files:
            print(f"{root}: no .rttm files found")
            continue
        ratios = []
        for rttm_path in rttm_files:
            turns = parse_rttm_turns(rttm_path.read_text(encoding="utf-8"))
            ratio = overlap_ratio(turns)
            ratios.append(ratio)
            print(f"{rttm_path}: overlap_ratio={ratio:.3f}")
        mean_ratio = sum(ratios) / len(ratios)
        print(f"=== {root}: {len(ratios)} file(s), mean overlap_ratio={mean_ratio:.3f} ===\n")


if __name__ == "__main__":
    main()
