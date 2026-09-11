"""R0 (research roadmap) local diarization evaluation framework --
provider-agnostic DER/JER measurement, inspired by (not copying) the
OpenBench/SDBench pattern of running the SAME fixtures through a pluggable
"subject" and measuring real, defined metrics -- see
`app.analytics.eval_engine`'s module docstring for the sibling
fact-extraction version of this same idea.

The one interface this module depends on is
`app.providers.diarization.DiarizationProvider` -- today only
`PyannoteDiarizationProvider`/`FakeDiarizationProvider` implement it, but
nothing here is pyannote-specific, so R1 (Sortformer) plugs in as a second
`DiarizationProvider` implementation with zero changes to this module. This
is the concrete mechanism that closes the test-infrastructure half of Phase
12 Finding #12 ("genuine multi-voice diarization accuracy has never been
empirically verified anywhere in this project") -- see
`app.analytics.diarization_fixtures` for what still has to be true of the
fixtures themselves for a given run to count as real evidence, not just a
framework existing.

Entirely local: `provider.diarize()` runs against a fixture's on-disk audio
file, no upload, no network call beyond whatever the provider's own
`diarize()` implementation already makes (none, for both providers that
exist today -- pyannote's pipeline is loaded from a local, pre-installed
snapshot per `docs/admin/model-installation.md`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.analytics.diarization_fixtures import DiarizationFixture
from app.analytics.diarization_metrics import DiarizationTurn, compute_der, compute_jer
from app.providers.diarization import DiarizationProvider


@dataclass(slots=True)
class FixtureEvalResult:
    fixture_id: str
    overlap_level: str
    der: float | None
    jer: float | None
    reference_speaker_count: int
    hypothesis_speaker_count: int | None
    duration_seconds: float
    error: str | None = None


@dataclass(slots=True)
class OverlapLevelSummary:
    overlap_level: str
    fixture_count: int
    mean_der: float | None
    mean_jer: float | None


@dataclass(slots=True)
class DiarizationEvalSummary:
    provider: str
    model: str
    model_revision: str | None
    fixture_source: str
    per_fixture: list[FixtureEvalResult] = field(default_factory=list)
    by_overlap_level: list[OverlapLevelSummary] = field(default_factory=list)
    mean_der: float | None = None
    mean_jer: float | None = None
    latency_seconds: float = 0.0

    def as_public_dict(self) -> dict[str, Any]:
        """What is actually persisted/returned over the API -- fixture ids
        (not audio content) and numeric metrics only, matching the same
        "never store transcript-shaped content" discipline
        `app.analytics.eval_engine.EvalResult.as_public_dict` follows."""
        return {
            "provider": self.provider,
            "model": self.model,
            "model_revision": self.model_revision,
            "fixture_source": self.fixture_source,
            "mean_der": self.mean_der,
            "mean_jer": self.mean_jer,
            "latency_seconds": round(self.latency_seconds, 3),
            "by_overlap_level": [
                {
                    "overlap_level": s.overlap_level,
                    "fixture_count": s.fixture_count,
                    "mean_der": s.mean_der,
                    "mean_jer": s.mean_jer,
                }
                for s in self.by_overlap_level
            ],
            "per_fixture": [
                {
                    "fixture_id": f.fixture_id,
                    "overlap_level": f.overlap_level,
                    "der": f.der,
                    "jer": f.jer,
                    "reference_speaker_count": f.reference_speaker_count,
                    "hypothesis_speaker_count": f.hypothesis_speaker_count,
                    "duration_seconds": round(f.duration_seconds, 3),
                    "error": f.error,
                }
                for f in self.per_fixture
            ],
        }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def run_diarization_eval(
    provider: DiarizationProvider,
    fixtures: list[DiarizationFixture],
    *,
    fixture_source: str,
) -> DiarizationEvalSummary:
    """Runs `provider.diarize()` on every fixture's audio file and scores
    the result against that fixture's RTTM ground truth. Never raises on a
    single fixture's failure (e.g. `DiarizationModelUnavailableError` if the
    real pyannote snapshot isn't installed in this environment) -- that
    fixture is recorded with `error` set and excluded from the aggregate
    means, so one missing/broken fixture doesn't hide every other result,
    matching `app.analytics.eval_engine.run_eval_subject`'s per-category
    error isolation."""
    status = provider.status()
    started = time.monotonic()
    per_fixture: list[FixtureEvalResult] = []

    for fixture in fixtures:
        try:
            result = await provider.diarize(fixture.audio_path)
        except Exception as exc:  # noqa: BLE001 - one bad fixture must not abort the run
            per_fixture.append(
                FixtureEvalResult(
                    fixture_id=fixture.fixture_id,
                    overlap_level=fixture.overlap_level,
                    der=None,
                    jer=None,
                    reference_speaker_count=len(
                        {t.speaker_label for t in fixture.reference_turns}
                    ),
                    hypothesis_speaker_count=None,
                    duration_seconds=fixture.duration_seconds,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        hypothesis_turns = [
            DiarizationTurn(t.start_seconds, t.end_seconds, t.speaker_label)
            for t in result.turns
        ]
        der_result = compute_der(fixture.reference_turns, hypothesis_turns)
        jer = compute_jer(fixture.reference_turns, hypothesis_turns)
        per_fixture.append(
            FixtureEvalResult(
                fixture_id=fixture.fixture_id,
                overlap_level=fixture.overlap_level,
                der=round(der_result.der, 4),
                jer=round(jer, 4),
                reference_speaker_count=len(
                    {t.speaker_label for t in fixture.reference_turns}
                ),
                hypothesis_speaker_count=result.speaker_count,
                duration_seconds=fixture.duration_seconds,
            )
        )

    elapsed = time.monotonic() - started

    by_overlap_level: list[OverlapLevelSummary] = []
    for overlap_level in ("none", "some", "heavy"):
        level_results = [f for f in per_fixture if f.overlap_level == overlap_level]
        ders = [f.der for f in level_results if f.der is not None]
        jers = [f.jer for f in level_results if f.jer is not None]
        if not level_results:
            continue
        by_overlap_level.append(
            OverlapLevelSummary(
                overlap_level=overlap_level,
                fixture_count=len(level_results),
                mean_der=_mean(ders),
                mean_jer=_mean(jers),
            )
        )

    all_ders = [f.der for f in per_fixture if f.der is not None]
    all_jers = [f.jer for f in per_fixture if f.jer is not None]

    return DiarizationEvalSummary(
        provider=status.provider,
        model=status.model,
        model_revision=status.model_revision,
        fixture_source=fixture_source,
        per_fixture=per_fixture,
        by_overlap_level=by_overlap_level,
        mean_der=_mean(all_ders),
        mean_jer=_mean(all_jers),
        latency_seconds=elapsed,
    )
