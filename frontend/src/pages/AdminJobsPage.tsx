import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listJobs, retryJob, type ProcessingJobSummary } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Button } from "../design-system/Button";
import { Select } from "../design-system/FormControls";
import { StatusBadge } from "../design-system/StatusBadge";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 7 Admin Portal Jobs page: real `ProcessingJob` rows (Phase 3,
 * hardened in Phase 3.1), not a mockup — with a retry action for
 * terminally FAILED jobs (reuses the existing retry mechanism, see
 * app.processing.service.retry_failed_job). Global/cross-organization
 * visibility is `system:admin`-gated.
 */
export function AdminJobsPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");

  const jobsQuery = useQuery({
    queryKey: ["admin", "jobs", statusFilter],
    queryFn: () => listJobs({ status: statusFilter || undefined, limit: 100 }),
  });

  async function handleRetry(jobId: string) {
    if (!csrfToken) return;
    await retryJob(jobId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "jobs"] });
  }

  const columns: DataTableColumn<ProcessingJobSummary>[] = [
    { key: "job_type", header: "Typ", render: (job) => job.job_type },
    { key: "status", header: "Status", render: (job) => <StatusBadge status={job.status} /> },
    { key: "attempt", header: "Versuch", render: (job) => `${job.attempt}/${job.max_attempts}` },
    { key: "queued_at", header: "Eingereiht am", render: (job) => new Date(job.queued_at).toLocaleString() },
    { key: "error", header: "Fehler", render: (job) => <span style={{ color: "var(--color-danger)" }}>{job.error_code ?? "—"}</span> },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Jobs</h1>
      <div style={{ margin: "var(--space-4) 0" }}>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Alle Status</option>
          <option value="queued">Wartend</option>
          <option value="running">Läuft</option>
          <option value="succeeded">Erfolgreich</option>
          <option value="failed">Fehlgeschlagen</option>
          <option value="cancelled">Abgebrochen</option>
        </Select>
      </div>

      <DataTable
        columns={columns}
        rows={jobsQuery.data?.items ?? []}
        keyExtractor={(job) => job.id}
        loading={jobsQuery.isLoading}
        rowActions={(job) =>
          job.status === "failed" ? (
            <Button variant="secondary" onClick={() => void handleRetry(job.id)}>
              Wiederholen
            </Button>
          ) : null
        }
      />
      {jobsQuery.data && (
        <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
          {jobsQuery.data.total} Job(s) insgesamt
        </p>
      )}
    </AdminLayout>
  );
}
