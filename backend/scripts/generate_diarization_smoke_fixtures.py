"""Regenerates `app/analytics/diarization_smoke_fixtures/` -- the tiny,
synthetic (two-tone, NOT real speech) fixtures that exercise the R0
diarization eval framework's wiring in mandatory CI (see
`app.analytics.diarization_fixtures`'s module docstring for why these are
deliberately NOT a substitute for the real FastMSS-generated batch).

Run with: `python scripts/generate_diarization_smoke_fixtures.py` from
`backend/`. Pure stdlib (`wave`, `math`, `struct`) -- no new dependency.
Deterministic: re-running always produces byte-identical output, so
regenerating and diffing is a legitimate way to confirm nothing else
changed these files by hand.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 8000
AMPLITUDE = 0.3  # of int16 full scale, headroom to avoid clipping on overlap

# Two distinct, fixed tones standing in for "two distinct voices" -- real
# fundamental-frequency separation, not a mockup. `overlap_level` describes
# how much of the two speakers' active time ranges coincide.
SPEAKER_A_HZ = 220.0
SPEAKER_B_HZ = 440.0


def _tone_samples(freq_hz: float, start: float, end: float, total_duration: float) -> list[float]:
    n_total = int(total_duration * SAMPLE_RATE)
    samples = [0.0] * n_total
    start_idx = int(start * SAMPLE_RATE)
    end_idx = int(end * SAMPLE_RATE)
    for i in range(max(0, start_idx), min(n_total, end_idx)):
        t = i / SAMPLE_RATE
        samples[i] = AMPLITUDE * math.sin(2 * math.pi * freq_hz * t)
    return samples


def _write_wav(path: Path, mixed: list[float]) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32768, min(32767, int(s * 32767)))) for s in mixed
        )
        handle.writeframes(frames)


def _write_rttm(path: Path, file_id: str, turns: list[tuple[float, float, str]]) -> None:
    lines = [
        f"SPEAKER {file_id} 1 {start:.3f} {end - start:.3f} <NA> <NA> {speaker} <NA> <NA>"
        for start, end, speaker in turns
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# (overlap_level, total_duration, [(speaker, start, end), ...])
FIXTURES: dict[str, tuple[float, list[tuple[str, float, float]]]] = {
    "none": (4.0, [("spk_a", 0.0, 2.0), ("spk_b", 2.0, 4.0)]),
    "some": (4.0, [("spk_a", 0.0, 2.5), ("spk_b", 1.5, 4.0)]),
    "heavy": (4.0, [("spk_a", 0.0, 4.0), ("spk_b", 0.5, 3.5)]),
}

FREQ_BY_SPEAKER = {"spk_a": SPEAKER_A_HZ, "spk_b": SPEAKER_B_HZ}


def main() -> None:
    out_root = Path(__file__).parent.parent / "app" / "analytics" / "diarization_smoke_fixtures"
    for overlap_level, (duration, turns) in FIXTURES.items():
        level_dir = out_root / overlap_level
        level_dir.mkdir(parents=True, exist_ok=True)
        fixture_id = f"smoke_two_speaker_{overlap_level}_overlap"

        mixed = [0.0] * int(duration * SAMPLE_RATE)
        for speaker, start, end in turns:
            tone = _tone_samples(FREQ_BY_SPEAKER[speaker], start, end, duration)
            mixed = [a + b for a, b in zip(mixed, tone, strict=True)]

        _write_wav(level_dir / f"{fixture_id}.wav", mixed)
        _write_rttm(
            level_dir / f"{fixture_id}.rttm",
            fixture_id,
            [(start, end, speaker) for speaker, start, end in turns],
        )
        print(f"wrote {level_dir / fixture_id}.{{wav,rttm}}")


if __name__ == "__main__":
    main()
