"""R0: end-to-end wiring test for the diarization eval framework -- fixture
discovery (RTTM parsing) -> `DiarizationProvider.diarize()` ->
DER/JER -- using `FakeDiarizationProvider` (the only diarization provider
available in mandatory CI; see .github/workflows/ci.yml's `backend` job,
which never installs the `ai` extra). This proves the framework's plumbing
end-to-end; it intentionally does NOT claim to prove real pyannote accuracy
-- see PHASE_R0_VALIDATION_REPORT.md's Known Limitations for the honest
line between the two.
"""

from __future__ import annotations

import pytest
from app.analytics.diarization_eval import run_diarization_eval
from app.analytics.diarization_fixtures import load_smoke_fixtures
from app.analytics.diarization_metrics import DiarizationTurn
from app.analytics.rttm import format_rttm, parse_rttm
from app.providers.diarization import FakeDiarizationProvider


def test_rttm_roundtrip() -> None:
    turns = [
        DiarizationTurn(0.0, 2.5, "SPEAKER_00"),
        DiarizationTurn(1.5, 4.0, "SPEAKER_01"),
    ]
    text = format_rttm(turns, file_id="unit_test")
    parsed = parse_rttm(text)
    assert parsed == turns


def test_load_smoke_fixtures_discovers_all_three_overlap_levels() -> None:
    fixtures = load_smoke_fixtures()
    levels = sorted({f.overlap_level for f in fixtures})
    assert levels == ["heavy", "none", "some"]
    for fixture in fixtures:
        assert fixture.reference_turns, fixture.fixture_id
        assert fixture.duration_seconds > 0
        assert fixture.source == "smoke"


@pytest.mark.asyncio
async def test_run_diarization_eval_against_fake_provider_end_to_end() -> None:
    fixtures = load_smoke_fixtures()
    provider = FakeDiarizationProvider()

    summary = await run_diarization_eval(provider, fixtures, fixture_source="smoke")

    assert summary.provider == "fake"
    assert summary.mean_der is not None
    assert {s.overlap_level for s in summary.by_overlap_level} == {"none", "some", "heavy"}
    assert len(summary.per_fixture) == len(fixtures)
    assert all(f.error is None for f in summary.per_fixture)
    public = summary.as_public_dict()
    assert public["mean_der"] == summary.mean_der
    assert len(public["per_fixture"]) == len(fixtures)


@pytest.mark.asyncio
async def test_run_diarization_eval_isolates_a_single_fixture_failure() -> None:
    """One fixture whose audio path doesn't exist / provider errors on
    must not abort the whole run -- matches
    `app.analytics.eval_engine.run_eval_subject`'s per-category isolation."""

    class _FlakyProvider(FakeDiarizationProvider):
        async def diarize(self, media_path: str, **kwargs: object) -> object:  # type: ignore[override]
            if "heavy" in media_path:
                raise RuntimeError("simulated provider failure")
            return await super().diarize(media_path, **kwargs)  # type: ignore[arg-type]

    fixtures = load_smoke_fixtures()
    summary = await run_diarization_eval(_FlakyProvider(), fixtures, fixture_source="smoke")

    failed = [f for f in summary.per_fixture if f.error is not None]
    succeeded = [f for f in summary.per_fixture if f.error is None]
    assert len(failed) == 1
    assert failed[0].overlap_level == "heavy"
    assert len(succeeded) == len(fixtures) - 1
