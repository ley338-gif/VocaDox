# Live-transcript scaling benchmark

Date: 2026-09-10

## Method

The benchmark models the exact audio seconds presented to the speech provider
and the encoded payload bytes uploaded by the current fixed ten-second cadence.
It is deterministic and hardware-independent:

```text
whole-prefix work = interval × N × (N + 1) / 2
rolling work      = recording duration + (N - 1) × overlap
N                 = recording duration / interval
```

Run it from `backend`:

```text
uv run python -m benchmarks.live_transcript_scaling \
  --durations 5 20 40 60 --interval 10 --overlap 2 \
  --bitrate-kbps 48 --rtf 0.25
```

The 48-kbit/s bitrate is a transparent comparison assumption, not a guarantee
about a browser's chosen Opus bitrate. Audio-work amplification does not depend
on bitrate. RTF 0.25 is an illustrative conversion (one second of compute per
four seconds of audio), not a measured claim about supported hardware.

## Results

| Duration | Flushes | Whole-prefix audio work | Whole-prefix amp. | Rolling audio work | Rolling amp. | Whole upload | Rolling upload | Whole compute @ RTF 0.25 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 min | 30 | 1.29 h | 15.5x | 0.10 h | 1.19x | 0.03 GiB | 0.002 GiB | 0.32 h |
| 20 min | 120 | 20.17 h | 60.5x | 0.40 h | 1.20x | 0.41 GiB | 0.008 GiB | 5.04 h |
| 40 min | 240 | 80.33 h | 120.5x | 0.80 h | 1.20x | 1.62 GiB | 0.016 GiB | 20.08 h |
| 60 min | 360 | 180.50 h | 180.5x | 1.20 h | 1.20x | 3.63 GiB | 0.024 GiB | 45.12 h |

The current endpoint also rejects a prefix above 25 MiB. At 48 kbit/s the
single growing prefix reaches that limit after about 73 minutes; at 96 kbit/s,
about 36 minutes. Browser-selected bitrates vary, so a 60-minute live preview
cannot be assumed to remain below the request limit.

## Interpretation

Whole-prefix retranscription is acceptable only as a bounded preview for short
recordings. For 20–60 minutes it creates quadratic provider work and cumulative
network traffic, makes update completion increasingly likely to exceed the
ten-second cadence, and may hit the request-size ceiling. Faster hardware does
not change the scaling law.

The overlap-window target stays close to linear: with ten seconds of new audio
and two seconds of overlap it processes approximately 1.2 times the recording
duration. See ADR-0045 for the target design and rollout gates.

## Limitations

No production speech model or representative deployment hardware was available
in this workspace, so wall-clock latency, peak memory, energy use, and WER are
not claimed. Those measurements are explicit rollout gates. This benchmark is
still sufficient to reject whole-prefix processing for long sessions because
its work amplification is exact and provider-independent.
