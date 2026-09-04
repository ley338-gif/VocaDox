"""Hard privacy rule (unchanged since Phase 1, re-verified for every new
admin surface every phase adds — see Phase 7's identical dashboard test):
no analytics/evaluation admin endpoint response may carry full
transcript/fact/document content. Technical/quality/correction analytics
are counts/rates only by construction (see app.analytics.service); this
test asserts the exact response key sets so a future change can't
accidentally add a content-carrying field without this test catching it.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.analytics.conftest import login


async def test_technical_analytics_response_shape_is_counts_only(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/analytics/technical", headers=headers)
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {
        "window_days",
        "total_jobs",
        "volume_by_day",
        "by_job_type",
    }


async def test_quality_metrics_response_shape_is_counts_only(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/analytics/quality", headers=headers)
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {
        "transcript_segments_total",
        "transcript_segments_corrected",
        "transcript_correction_rate",
        "fact_review_status_counts",
        "facts_total",
        "fact_corrected_or_removed_rate",
        "review_issue_status_counts",
        "review_issue_resolution_counts",
    }


async def test_correction_metrics_response_shape_is_counts_only(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.get("/api/v1/admin/analytics/corrections", headers=headers)
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {
        "fact_corrections_by_category",
        "most_corrected_subjects",
        "transcript_segment_corrections_total",
    }


async def test_evaluation_run_response_never_carries_transcript_text(
    client: AsyncClient, seeded  # noqa: ANN001
) -> None:
    """The per-category eval result carries item COUNTS
    (`item_count`)/booleans only — never the actual extracted item
    payloads (subject/value/description text), even for the synthetic
    fixture."""
    headers = await login(client, "carol", "yet another strong pw 789")
    resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": "Privacy test model",
            "purpose": "extraction",
            "provider": "fake",
            "model_identifier": "fake-llm-v0",
        },
        headers=headers,
    )
    profile_a = resp.json()["id"]
    resp = await client.post(
        "/api/v1/model-profiles",
        json={
            "name": "Privacy test model 2",
            "purpose": "extraction",
            "provider": "fake",
            "model_identifier": "fake-llm-v0",
        },
        headers=headers,
    )
    profile_b = resp.json()["id"]

    resp = await client.post(
        "/api/v1/admin/evaluation/model-comparison",
        json={"model_profile_id_a": profile_a, "model_profile_id_b": profile_b},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    result_a = resp.json()["result_a"]
    assert set(result_a.keys()) == {
        "label",
        "facts_expected",
        "facts_matched",
        "evidence_linkage_rate",
        "contradictions_expected",
        "contradictions_detected",
        "json_valid_categories",
        "json_total_categories",
        "latency_seconds",
        "per_category",
        "error",
    }
    for category in result_a["per_category"]:
        assert set(category.keys()) == {"category", "json_valid", "item_count", "error"}
