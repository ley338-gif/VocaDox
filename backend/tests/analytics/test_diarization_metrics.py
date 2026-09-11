"""R0: unit tests for the DER/JER metric implementation
(app.analytics.diarization_metrics) -- pure numeric tests, no audio, no
provider, no DB. These are the load-bearing tests proving the metric
implementation itself is correct: speaker-label-permutation invariance,
sensitivity to missed speakers/false alarms/confusion, and -- the concrete
claim R0's validation report has to be able to make -- that DER responds
correctly to increasing overlap severity."""

from __future__ import annotations

from app.analytics.diarization_metrics import DiarizationTurn, compute_der, compute_jer


def _turn(start: float, end: float, speaker: str) -> DiarizationTurn:
    return DiarizationTurn(start_seconds=start, end_seconds=end, speaker_label=speaker)


def test_perfect_match_scores_zero() -> None:
    reference = [_turn(0.0, 2.0, "A"), _turn(2.0, 4.0, "B")]
    result = compute_der(reference, reference)
    assert result.der == 0.0
    assert compute_jer(reference, reference) == 0.0


def test_label_permutation_is_invariant() -> None:
    """The hypothesis's speaker labels are arbitrary (a provider has no
    reason to call anyone "A" or "spk_a") -- DER/JER must be computed after
    finding the best label mapping, not by comparing labels literally."""
    reference = [_turn(0.0, 2.0, "A"), _turn(2.0, 4.0, "B")]
    hypothesis = [_turn(0.0, 2.0, "SPEAKER_07"), _turn(2.0, 4.0, "SPEAKER_02")]
    result = compute_der(reference, hypothesis)
    assert result.der == 0.0
    assert result.speaker_mapping == {"SPEAKER_07": "A", "SPEAKER_02": "B"}


def test_total_miss_scores_der_one() -> None:
    reference = [_turn(0.0, 2.0, "A"), _turn(2.0, 4.0, "B")]
    result = compute_der(reference, [])
    assert result.der == 1.0
    assert result.missed_speech == 4.0


def test_false_alarm_only_when_reference_silent() -> None:
    reference: list[DiarizationTurn] = []
    hypothesis = [_turn(0.0, 2.0, "A")]
    result = compute_der(reference, hypothesis)
    # No reference speech to normalize by -- but real (non-silent) false
    # alarm must not be silently scored as a vacuous 0.0.
    assert result.der == 1.0


def test_speaker_confusion_detected_when_turns_swapped() -> None:
    reference = [_turn(0.0, 2.0, "A"), _turn(2.0, 4.0, "B")]
    # Hypothesis assigns the FIRST turn's time range to "B" and the
    # second's to "A" -- i.e. gets the turns right but the speaker
    # identities backwards relative to any single consistent mapping.
    hypothesis = [_turn(0.0, 2.0, "A"), _turn(2.0, 3.0, "A"), _turn(3.0, 4.0, "B")]
    result = compute_der(reference, hypothesis)
    assert result.der > 0.0
    assert result.confusion > 0.0


def test_jer_penalizes_a_completely_missed_quiet_speaker_even_with_low_der() -> None:
    """The concrete failure mode DER alone can hide, and JER exists to
    catch (Ryant et al. 2019): one dominant, correctly-diarized speaker
    plus one totally missed quiet speaker can still show a deceptively low
    DER (since DER is time-weighted and the quiet speaker contributes
    little reference time), but JER -- an unweighted per-speaker mean --
    must not hide it."""
    reference = [
        _turn(0.0, 19.0, "A"),  # dominant speaker, 19s
        _turn(19.0, 20.0, "B"),  # quiet speaker, 1s, totally missed below
    ]
    hypothesis = [_turn(0.0, 20.0, "A")]  # never detects a second speaker at all
    der_result = compute_der(reference, hypothesis)
    jer = compute_jer(reference, hypothesis)
    assert der_result.der < 0.10  # DER alone looks deceptively good
    assert jer > 0.45  # JER's unweighted mean surfaces the fully-missed speaker


def test_der_increases_with_overlap_severity_for_a_realistic_hypothesis_degradation() -> None:
    """The concrete empirical claim this framework has to be able to
    support: a hypothesis that is accurate when speakers don't overlap but
    (like most real diarizers, pyannote included -- see
    docs/architecture/diarization.md's overlap-handling section) only
    reports ONE active speaker during any period of true overlap, must
    score a strictly worse DER as overlap severity increases across the
    three fixture levels this project uses (none/some/heavy) -- proving
    the metric is actually sensitive to overlap, not just to gross errors.
    Mirrors the three `app.analytics.diarization_smoke_fixtures` fixture
    definitions (see `backend/scripts/generate_diarization_smoke_fixtures.py`).
    """

    def hypothesize_single_speaker_during_overlap(
        reference: list[DiarizationTurn],
    ) -> list[DiarizationTurn]:
        """A crude but realistic stand-in for "detects both speakers
        individually, but collapses any overlapping region onto whichever
        speaker started it" -- exactly the exclusive_speaker_diarization
        behavior `app/providers/diarization.py`'s docstring explicitly
        warns against relying on."""
        boundaries = sorted(
            {t.start_seconds for t in reference} | {t.end_seconds for t in reference}
        )
        out: list[DiarizationTurn] = []
        for i in range(len(boundaries) - 1):
            seg_start, seg_end = boundaries[i], boundaries[i + 1]
            active = [
                t
                for t in reference
                if t.start_seconds <= seg_start and seg_end <= t.end_seconds
            ]
            if not active:
                continue
            # Collapse overlapping active speakers onto the first (by
            # reference order) -- i.e. exactly one hypothesis speaker per
            # interval, regardless of how many were truly active.
            out.append(_turn(seg_start, seg_end, active[0].speaker_label))
        return out

    fixtures = {
        "none": [_turn(0.0, 2.0, "spk_a"), _turn(2.0, 4.0, "spk_b")],
        "some": [_turn(0.0, 2.5, "spk_a"), _turn(1.5, 4.0, "spk_b")],
        "heavy": [_turn(0.0, 4.0, "spk_a"), _turn(0.5, 3.5, "spk_b")],
    }

    ders = {}
    for level, reference in fixtures.items():
        hypothesis = hypothesize_single_speaker_during_overlap(reference)
        ders[level] = compute_der(reference, hypothesis).der

    assert ders["none"] < ders["some"] < ders["heavy"], ders
