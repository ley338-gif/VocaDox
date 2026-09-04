"""GET /admin/analytics/quality and /admin/analytics/corrections (Phase 8)
— real, precisely-defined descriptive statistics over the Phase 3/4/5
correction-feedback tables. Verified against directly-inserted rows with
known counts so every computed rate is checkable exactly."""

from __future__ import annotations

import uuid

import pytest
from app.intelligence.models import ExtractedFact, FactCorrection, FactReviewStatus, FactStatus
from app.review.models import (
    ReviewIssue,
    ReviewIssueResolution,
    ReviewIssueStatus,
    ReviewIssueType,
)
from app.transcription.models import (
    Transcript,
    TranscriptSegment,
    TranscriptSegmentCorrection,
)
from httpx import AsyncClient

from tests.analytics.conftest import login


async def test_quality_metrics_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/analytics/quality", headers=headers)
    assert resp.status_code == 403


async def test_correction_metrics_requires_permission(client: AsyncClient, seeded) -> None:  # noqa: ANN001
    headers = await login(client, "alice", "a very strong password 123")
    resp = await client.get("/api/v1/admin/analytics/corrections", headers=headers)
    assert resp.status_code == 403


async def test_quality_and_correction_metrics_real_rates(
    client: AsyncClient, app_env, seeded  # noqa: ANN001
) -> None:
    app, sessionmaker = app_env
    conversation_id = uuid.uuid4()
    async with sessionmaker() as session:
        transcript = Transcript(
            conversation_id=conversation_id,
            source_media_id=uuid.uuid4(),
            provider="fake",
            model="fake",
        )
        session.add(transcript)
        await session.flush()

        # 3 segments total, 1 corrected -> correction rate 1/3.
        segments = [
            TranscriptSegment(
                transcript_id=transcript.id,
                sequence=i,
                start_ms=i * 1000,
                end_ms=(i + 1) * 1000,
                original_text=f"segment {i}",
            )
            for i in range(3)
        ]
        session.add_all(segments)
        await session.flush()
        session.add(
            TranscriptSegmentCorrection(
                segment_id=segments[0].id,
                previous_corrected_text=None,
                new_corrected_text="corrected segment 0",
            )
        )

        # 4 facts: 1 confirmed, 1 corrected, 1 removed, 1 pending ->
        # corrected_or_removed rate = 2/4 = 0.5.
        facts = []
        for i, review_status in enumerate(
            [
                FactReviewStatus.CONFIRMED.value,
                FactReviewStatus.CORRECTED.value,
                FactReviewStatus.REMOVED.value,
                FactReviewStatus.PENDING.value,
            ]
        ):
            fact = ExtractedFact(
                conversation_id=conversation_id,
                category="general_fact",
                fact_type="general_fact",
                structured_value={"subject": f"Drug{i}", "attribute": "dose", "value": "5mg"},
                certainty="stated",
                status=FactStatus.VERIFIED.value,
                review_status=review_status,
            )
            session.add(fact)
            facts.append(fact)
        await session.flush()

        # 2 correction events on the same fact's subject "DrugX" so
        # most_corrected_subjects is checkable.
        session.add(
            FactCorrection(
                fact_id=facts[1].id,
                previous_structured_value={"subject": "DrugX", "attribute": "dose", "value": "5mg"},
                new_structured_value={"subject": "DrugX", "attribute": "dose", "value": "10mg"},
            )
        )
        session.add(
            FactCorrection(
                fact_id=facts[1].id,
                previous_structured_value={
                    "subject": "DrugX", "attribute": "dose", "value": "10mg"
                },
                new_structured_value={"subject": "DrugX", "attribute": "dose", "value": "15mg"},
            )
        )

        # 2 review issues: one resolved (corrected), one still open.
        session.add(
            ReviewIssue(
                conversation_id=conversation_id,
                issue_type=ReviewIssueType.UNCERTAINTY.value,
                severity="low",
                related_fact_ids=[str(facts[1].id)],
                description="test issue 1",
                status=ReviewIssueStatus.RESOLVED.value,
                resolved_status=ReviewIssueResolution.CORRECTED.value,
            )
        )
        session.add(
            ReviewIssue(
                conversation_id=conversation_id,
                issue_type=ReviewIssueType.UNCERTAINTY.value,
                severity="low",
                related_fact_ids=[str(facts[3].id)],
                description="test issue 2",
                status=ReviewIssueStatus.OPEN.value,
            )
        )
        await session.commit()

    headers = await login(client, "carol", "yet another strong pw 789")

    resp = await client.get("/api/v1/admin/analytics/quality", headers=headers)
    assert resp.status_code == 200, resp.text
    quality = resp.json()
    assert quality["transcript_segments_total"] == 3
    assert quality["transcript_segments_corrected"] == 1
    assert quality["transcript_correction_rate"] == pytest.approx(1 / 3)
    assert quality["facts_total"] == 4
    assert quality["fact_corrected_or_removed_rate"] == pytest.approx(0.5)
    assert quality["review_issue_status_counts"]["resolved"] == 1
    assert quality["review_issue_status_counts"]["open"] == 1
    assert quality["review_issue_resolution_counts"]["corrected"] == 1
    # Never any transcript/fact content leaks into the response.
    assert set(quality.keys()) == {
        "transcript_segments_total",
        "transcript_segments_corrected",
        "transcript_correction_rate",
        "fact_review_status_counts",
        "facts_total",
        "fact_corrected_or_removed_rate",
        "review_issue_status_counts",
        "review_issue_resolution_counts",
    }

    resp = await client.get("/api/v1/admin/analytics/corrections", headers=headers)
    assert resp.status_code == 200, resp.text
    corrections = resp.json()
    assert corrections["fact_corrections_by_category"]["general_fact"] == 2
    assert corrections["transcript_segment_corrections_total"] == 1
    subjects = {s["subject"]: s["count"] for s in corrections["most_corrected_subjects"]}
    assert subjects["DrugX"] == 2
