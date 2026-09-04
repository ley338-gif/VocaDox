import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getCorrectionMetrics, getQualityMetrics, getTechnicalAnalytics } from "../api/analytics";
import { AdminLayout } from "../components/AdminLayout";

type Tab = "technical" | "quality" | "corrections";

function formatRate(rate: number | null): string {
  return rate === null ? "n/a" : `${(rate * 100).toFixed(1)}%`;
}

/**
 * Phase 8 Admin Portal Analytics page (spec roadmap §73): technical
 * analytics (real ProcessingJob volume/success-rate/latency, Phase 3
 * data), quality metrics (real transcript/fact correction rates, Phase
 * 3/5 data), and correction metrics (real correction-feedback frequency,
 * Phase 3/5 data) — every number here is a real, precisely-defined
 * descriptive statistic (see each backend endpoint's docstring), never a
 * fabricated "AI accuracy" figure. Structurally cannot leak conversation/
 * fact/transcript content: the backend responses are counts/rates only
 * (see tests/analytics/test_privacy.py).
 */
export function AdminAnalyticsPage() {
  const [tab, setTab] = useState<Tab>("technical");

  const technicalQuery = useQuery({
    queryKey: ["admin", "analytics", "technical"],
    queryFn: () => getTechnicalAnalytics(30),
    enabled: tab === "technical",
  });
  const qualityQuery = useQuery({
    queryKey: ["admin", "analytics", "quality"],
    queryFn: getQualityMetrics,
    enabled: tab === "quality",
  });
  const correctionsQuery = useQuery({
    queryKey: ["admin", "analytics", "corrections"],
    queryFn: getCorrectionMetrics,
    enabled: tab === "corrections",
  });

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Analytics
      </h1>
      <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
        {(["technical", "quality", "corrections"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "var(--space-2) var(--space-3)",
              border: "none",
              borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
              background: "transparent",
              fontWeight: tab === t ? 600 : 400,
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "technical" && technicalQuery.data && (
        <section style={{ marginTop: "var(--space-6)" }}>
          <p style={{ color: "var(--text-muted)" }}>
            Last {technicalQuery.data.window_days} days — {technicalQuery.data.total_jobs} total
            job(s).
          </p>
          <table style={{ width: "100%", marginTop: "var(--space-4)", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                <th>Job type</th>
                <th>Queued</th>
                <th>Running</th>
                <th>Succeeded</th>
                <th>Failed</th>
                <th>Success rate</th>
                <th>Avg latency</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(technicalQuery.data.by_job_type).map(([jobType, counts]) => (
                <tr key={jobType} style={{ borderBottom: "1px solid var(--border-default)" }}>
                  <td>{jobType}</td>
                  <td>{counts.queued}</td>
                  <td>{counts.running}</td>
                  <td>{counts.succeeded}</td>
                  <td>{counts.failed}</td>
                  <td>{formatRate(counts.success_rate)}</td>
                  <td>
                    {counts.avg_latency_seconds === null
                      ? "n/a"
                      : `${counts.avg_latency_seconds.toFixed(1)}s`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "quality" && qualityQuery.data && (
        <section style={{ marginTop: "var(--space-6)" }}>
          <div style={{ display: "flex", gap: "var(--space-6)", flexWrap: "wrap" }}>
            <div>
              <div style={{ color: "var(--text-muted)" }}>Transcript correction rate</div>
              <div style={{ fontSize: "var(--font-h2-size)" }}>
                {formatRate(qualityQuery.data.transcript_correction_rate)}
              </div>
              <div style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
                {qualityQuery.data.transcript_segments_corrected} of{" "}
                {qualityQuery.data.transcript_segments_total} segments corrected
              </div>
            </div>
            <div>
              <div style={{ color: "var(--text-muted)" }}>Fact corrected-or-removed rate</div>
              <div style={{ fontSize: "var(--font-h2-size)" }}>
                {formatRate(qualityQuery.data.fact_corrected_or_removed_rate)}
              </div>
              <div style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
                {qualityQuery.data.facts_total} facts total
              </div>
            </div>
          </div>
          <div style={{ marginTop: "var(--space-6)", display: "flex", gap: "var(--space-8)" }}>
            <div>
              <h3 style={{ fontSize: "var(--font-h3-size)" }}>Fact review status</h3>
              <ul>
                {Object.entries(qualityQuery.data.fact_review_status_counts).map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 style={{ fontSize: "var(--font-h3-size)" }}>Review issue resolution</h3>
              <ul>
                {Object.entries(qualityQuery.data.review_issue_resolution_counts).map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {tab === "corrections" && correctionsQuery.data && (
        <section style={{ marginTop: "var(--space-6)" }}>
          <h3 style={{ fontSize: "var(--font-h3-size)" }}>Corrections by fact category</h3>
          <ul>
            {Object.entries(correctionsQuery.data.fact_corrections_by_category).map(([k, v]) => (
              <li key={k}>
                {k}: {v}
              </li>
            ))}
          </ul>
          <h3 style={{ fontSize: "var(--font-h3-size)", marginTop: "var(--space-6)" }}>
            Most-corrected subjects
          </h3>
          <ul>
            {correctionsQuery.data.most_corrected_subjects.map((s) => (
              <li key={s.subject}>
                {s.subject}: {s.count}
              </li>
            ))}
          </ul>
          <p style={{ marginTop: "var(--space-6)", color: "var(--text-muted)" }}>
            {correctionsQuery.data.transcript_segment_corrections_total} total transcript segment
            correction(s).
          </p>
        </section>
      )}
    </AdminLayout>
  );
}
