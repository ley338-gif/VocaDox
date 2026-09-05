import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getCorrectionMetrics, getQualityMetrics, getTechnicalAnalytics } from "../api/analytics";
import { AdminLayout } from "../components/AdminLayout";
import { StatCard } from "../design-system/Card";
import { TabPanel, Tabs } from "../design-system/Tabs";
import { DataTable, type DataTableColumn } from "../design-system/Table";

type Tab = "technical" | "quality" | "corrections";

function formatRate(rate: number | null): string {
  return rate === null ? "k. A." : `${(rate * 100).toFixed(1)}%`;
}

interface JobTypeRow {
  jobType: string;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  avg_latency_seconds: number | null;
}

const TAB_ITEMS = [
  { id: "technical", label: "Technisch" },
  { id: "quality", label: "Qualität" },
  { id: "corrections", label: "Korrekturen" },
];

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

  const jobTypeColumns: DataTableColumn<JobTypeRow>[] = [
    { key: "jobType", header: "Job-Typ", render: (r) => r.jobType },
    { key: "queued", header: "Wartend", render: (r) => r.queued },
    { key: "running", header: "Läuft", render: (r) => r.running },
    { key: "succeeded", header: "Erfolgreich", render: (r) => r.succeeded },
    { key: "failed", header: "Fehlgeschlagen", render: (r) => r.failed },
    { key: "rate", header: "Erfolgsrate", render: (r) => formatRate(r.success_rate) },
    { key: "latency", header: "Ø Latenz", render: (r) => (r.avg_latency_seconds === null ? "k. A." : `${r.avg_latency_seconds.toFixed(1)}s`) },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)", marginBottom: "var(--space-4)" }}>
        Analytics
      </h1>
      <Tabs items={TAB_ITEMS} activeId={tab} onChange={(id) => setTab(id as Tab)} idPrefix="analytics" />

      <TabPanel id="technical" activeId={tab} idPrefix="analytics">
        {technicalQuery.data && (
          <>
            <p style={{ color: "var(--text-muted)", marginBottom: "var(--space-3)" }}>
              Letzte {technicalQuery.data.window_days} Tage — {technicalQuery.data.total_jobs} Job(s) insgesamt.
            </p>
            <DataTable
              columns={jobTypeColumns}
              rows={Object.entries(technicalQuery.data.by_job_type).map(([jobType, counts]) => ({ jobType, ...counts }))}
              keyExtractor={(r) => r.jobType}
            />
          </>
        )}
      </TabPanel>

      <TabPanel id="quality" activeId={tab} idPrefix="analytics">
        {qualityQuery.data && (
          <>
            <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
              <StatCard
                label="Transkript-Korrekturrate"
                value={formatRate(qualityQuery.data.transcript_correction_rate)}
                hint={`${qualityQuery.data.transcript_segments_corrected} von ${qualityQuery.data.transcript_segments_total} Segmenten korrigiert`}
              />
              <StatCard
                label="Fakten korrigiert/entfernt"
                value={formatRate(qualityQuery.data.fact_corrected_or_removed_rate)}
                hint={`${qualityQuery.data.facts_total} Fakten insgesamt`}
              />
            </div>
            <div style={{ marginTop: "var(--space-6)", display: "flex", gap: "var(--space-8)", flexWrap: "wrap" }}>
              <div>
                <h3 style={{ fontSize: "var(--font-h3-size)" }}>Fakten-Review-Status</h3>
                <ul>
                  {Object.entries(qualityQuery.data.fact_review_status_counts).map(([k, v]) => (
                    <li key={k}>
                      {k}: {v}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 style={{ fontSize: "var(--font-h3-size)" }}>Auflösung von Review-Hinweisen</h3>
                <ul>
                  {Object.entries(qualityQuery.data.review_issue_resolution_counts).map(([k, v]) => (
                    <li key={k}>
                      {k}: {v}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        )}
      </TabPanel>

      <TabPanel id="corrections" activeId={tab} idPrefix="analytics">
        {correctionsQuery.data && (
          <>
            <h3 style={{ fontSize: "var(--font-h3-size)" }}>Korrekturen nach Fakt-Kategorie</h3>
            <ul>
              {Object.entries(correctionsQuery.data.fact_corrections_by_category).map(([k, v]) => (
                <li key={k}>
                  {k}: {v}
                </li>
              ))}
            </ul>
            <h3 style={{ fontSize: "var(--font-h3-size)", marginTop: "var(--space-6)" }}>
              Am häufigsten korrigierte Subjekte
            </h3>
            <ul>
              {correctionsQuery.data.most_corrected_subjects.map((s) => (
                <li key={s.subject}>
                  {s.subject}: {s.count}
                </li>
              ))}
            </ul>
            <p style={{ marginTop: "var(--space-6)", color: "var(--text-muted)" }}>
              {correctionsQuery.data.transcript_segment_corrections_total} Transkriptsegment-Korrektur(en) insgesamt.
            </p>
          </>
        )}
      </TabPanel>
    </AdminLayout>
  );
}
