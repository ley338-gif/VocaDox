"""Diarization Error Rate (DER) and Jaccard Error Rate (JER) -- R0 (research
roadmap, post-GA) real, standard diarization-accuracy metrics, computed over
a reference (ground truth) and hypothesis (provider output) set of speaker
turns. Pure stdlib, no new dependency -- same discipline as
`app.analytics.wer.word_error_rate`.

Both metrics are defined exactly as NIST RT / DIHARD define them (see
docstrings below), including honest handling of overlapping speech (multiple
simultaneous speakers in either reference or hypothesis) rather than
silently assuming one-speaker-at-a-time -- consistent with
`app.providers.diarization`'s "overlapping speech is represented honestly"
rule and `docs/architecture/diarization.md`'s overlap-handling section.

Speaker-label mapping between reference and hypothesis is solved by exact
search over all permutations of the smaller label set (diarization runs in
this project are always small -- a handful of speakers per conversation --
so this stays fast without pulling in scipy/Hungarian-algorithm-via-numpy
just for this). This mirrors the optimal-mapping approach pyannote.metrics
uses (solved there via scipy's linear_sum_assignment); the objective
(maximize total time-overlap under the mapping) is identical.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiarizationTurn:
    """One speaker turn, provider- and ground-truth-agnostic. Mirrors the
    shape of `app.providers.diarization.SpeakerTurn` but deliberately kept
    separate/minimal -- this module must stay provider-agnostic and must
    not import anything from `app.providers.diarization` (R1 will feed it
    turns produced by a second, different provider)."""

    start_seconds: float
    end_seconds: float
    speaker_label: str


@dataclass(frozen=True, slots=True)
class DerResult:
    der: float
    missed_speech: float
    false_alarm: float
    confusion: float
    total_reference_speech_seconds: float
    # The mapping actually chosen (hypothesis_label -> reference_label),
    # for transparency/debugging -- e.g. surfacing in the Evaluation Lab UI
    # which detected speaker was scored against which ground-truth speaker.
    speaker_mapping: dict[str, str]


def _boundaries(turns: list[DiarizationTurn]) -> list[float]:
    points: set[float] = set()
    for t in turns:
        points.add(t.start_seconds)
        points.add(t.end_seconds)
    return sorted(points)


def _active_speakers_by_interval(
    turns: list[DiarizationTurn], boundaries: list[float]
) -> list[set[str]]:
    """One `set[str]` of active speaker labels per interval between
    consecutive boundary points (len(boundaries) - 1 intervals). A turn
    covers an interval when the turn strictly contains it (start <= interval
    start and interval end <= turn end) -- since `boundaries` already
    includes every turn's own start/end, this exactly reconstructs which
    turns were active in each interval, overlapping turns included."""
    result: list[set[str]] = []
    for i in range(len(boundaries) - 1):
        seg_start, seg_end = boundaries[i], boundaries[i + 1]
        active = {
            t.speaker_label
            for t in turns
            if t.start_seconds <= seg_start and seg_end <= t.end_seconds
        }
        result.append(active)
    return result


def _overlap_matrix(
    ref_by_interval: list[set[str]],
    hyp_by_interval: list[set[str]],
    durations: list[float],
) -> dict[tuple[str, str], float]:
    overlap: dict[tuple[str, str], float] = {}
    for ref_active, hyp_active, duration in zip(
        ref_by_interval, hyp_by_interval, durations, strict=True
    ):
        for r in ref_active:
            for h in hyp_active:
                overlap[(r, h)] = overlap.get((r, h), 0.0) + duration
    return overlap


def _best_mapping(
    ref_labels: list[str],
    hyp_labels: list[str],
    overlap: dict[tuple[str, str], float],
) -> dict[str, str]:
    """Exact search over all injective mappings hyp_label -> ref_label
    (padding the shorter side with `None` so every hypothesis/reference
    label gets exactly one counterpart or none), maximizing total
    time-overlap. Returns hyp_label -> ref_label for matched pairs only."""
    if not ref_labels or not hyp_labels:
        return {}

    # Search over permutations of the smaller side assigned onto the
    # larger side's positions (standard trick to keep permutation count
    # bounded by min(|ref|, |hyp|)! rather than max(...)!).
    if len(hyp_labels) <= len(ref_labels):
        small, large = hyp_labels, ref_labels
        small_is_hyp = True
    else:
        small, large = ref_labels, hyp_labels
        small_is_hyp = False

    best_score = -1.0
    best_pairs: list[tuple[str, str]] = []
    for large_subset in itertools.permutations(large, len(small)):
        pairs = list(zip(small, large_subset, strict=True))
        score = 0.0
        for a, b in pairs:
            key = (a, b) if not small_is_hyp else (b, a)
            score += overlap.get(key, 0.0)
        if score > best_score:
            best_score = score
            best_pairs = pairs

    if small_is_hyp:
        return {hyp: ref for hyp, ref in best_pairs}
    return {hyp: ref for ref, hyp in best_pairs}


def compute_der(
    reference: list[DiarizationTurn], hypothesis: list[DiarizationTurn]
) -> DerResult:
    """Standard NIST-style Diarization Error Rate, generalized to
    overlapping speech exactly as pyannote.metrics/dscore define it:

        DER = (missed_speech + false_alarm + confusion) / total_reference_speech

    computed per fine-grained interval (every distinct turn boundary), where
    for each interval with `n_ref` reference speakers active and `n_hyp`
    (optimally-mapped) hypothesis speakers active, `n_correct` of which
    match:
        missed_speech += max(0, n_ref - n_hyp) * interval_duration
        false_alarm    += max(0, n_hyp - n_ref) * interval_duration
        confusion      += (min(n_ref, n_hyp) - n_correct) * interval_duration

    `total_reference_speech` sums `n_ref * interval_duration` over every
    interval (an interval with 2 simultaneous reference speakers counts
    double, matching how NIST scores overlapping ground truth).

    Returns DER=0.0 (perfect, vacuous score) with an empty mapping when the
    reference contains no speech at all -- there is nothing to get wrong.
    """
    boundaries = _boundaries(reference + hypothesis)
    if len(boundaries) < 2:
        return DerResult(0.0, 0.0, 0.0, 0.0, 0.0, {})

    durations = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
    ref_by_interval = _active_speakers_by_interval(reference, boundaries)
    hyp_by_interval = _active_speakers_by_interval(hypothesis, boundaries)

    ref_labels = sorted({t.speaker_label for t in reference})
    hyp_labels = sorted({t.speaker_label for t in hypothesis})
    overlap = _overlap_matrix(ref_by_interval, hyp_by_interval, durations)
    mapping = _best_mapping(ref_labels, hyp_labels, overlap)  # hyp -> ref

    total_ref_speech = 0.0
    missed = 0.0
    false_alarm = 0.0
    confusion = 0.0
    for ref_active, hyp_active, duration in zip(
        ref_by_interval, hyp_by_interval, durations, strict=True
    ):
        n_ref = len(ref_active)
        total_ref_speech += n_ref * duration
        mapped_hyp_active = {mapping.get(h, h) for h in hyp_active}
        n_hyp = len(hyp_active)
        n_correct = len(ref_active & mapped_hyp_active)
        missed += max(0, n_ref - n_hyp) * duration
        false_alarm += max(0, n_hyp - n_ref) * duration
        confusion += (min(n_ref, n_hyp) - n_correct) * duration

    if total_ref_speech <= 0.0:
        der = 0.0 if (missed + false_alarm + confusion) == 0.0 else 1.0
    else:
        der = (missed + false_alarm + confusion) / total_ref_speech

    return DerResult(
        der=der,
        missed_speech=missed,
        false_alarm=false_alarm,
        confusion=confusion,
        total_reference_speech_seconds=total_ref_speech,
        speaker_mapping=mapping,
    )


def compute_jer(
    reference: list[DiarizationTurn], hypothesis: list[DiarizationTurn]
) -> float:
    """Jaccard Error Rate (Ryant et al., DIHARD II, 2019): for each
    reference speaker matched (by the same optimal mapping `compute_der`
    uses) to a hypothesis speaker, the per-speaker error is
    `1 - |intersection| / |union|` of their active-time sets; an unmatched
    reference speaker (more reference speakers than hypothesis speakers)
    scores the maximum error of 1.0 for lacking any counterpart at all.
    JER is the unweighted mean of these per-reference-speaker scores --
    unlike DER, it does not let one dominant speaker's accuracy hide a
    completely missed quiet speaker, which is exactly the failure mode a
    same-synthetic-voice-at-different-playback-rates fixture (Phase 12
    Finding #12) could never surface.
    """
    ref_labels = sorted({t.speaker_label for t in reference})
    if not ref_labels:
        return 0.0

    boundaries = _boundaries(reference + hypothesis)
    durations = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
    ref_by_interval = _active_speakers_by_interval(reference, boundaries) if boundaries else []
    hyp_by_interval = _active_speakers_by_interval(hypothesis, boundaries) if boundaries else []
    hyp_labels = sorted({t.speaker_label for t in hypothesis})
    overlap = _overlap_matrix(ref_by_interval, hyp_by_interval, durations)
    mapping = _best_mapping(ref_labels, hyp_labels, overlap)  # hyp -> ref
    ref_to_hyp = {ref: hyp for hyp, ref in mapping.items()}

    ref_active_time = {label: 0.0 for label in ref_labels}
    hyp_active_time = {label: 0.0 for label in hyp_labels}
    for ref_active, hyp_active, duration in zip(
        ref_by_interval, hyp_by_interval, durations, strict=True
    ):
        for label in ref_active:
            ref_active_time[label] += duration
        for label in hyp_active:
            hyp_active_time[label] += duration

    errors: list[float] = []
    for ref_label in ref_labels:
        hyp_label = ref_to_hyp.get(ref_label)
        if hyp_label is None:
            errors.append(1.0)
            continue
        intersection = overlap.get((ref_label, hyp_label), 0.0)
        union = ref_active_time[ref_label] + hyp_active_time[hyp_label] - intersection
        errors.append(0.0 if union <= 0.0 else 1.0 - (intersection / union))

    return sum(errors) / len(errors)
