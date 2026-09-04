import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listJobs, retryJob } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Select } from "../design-system/FormControls";

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  queued: "info",
  running: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
};

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

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Jobs</h1>
      <div style={{ marginTop: "var(--space-4)" }}>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </div>

      <table style={{ width: "100%", marginTop: "var(--space-4)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Type</th>
            <th>Status</th>
            <th>Attempt</th>
            <th>Queued at</th>
            <th>Error</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {jobsQuery.data?.items.map((job) => (
            <tr key={job.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{job.job_type}</td>
              <td>
                <Badge tone={STATUS_TONE[job.status] ?? "neutral"}>{job.status}</Badge>
              </td>
              <td>
                {job.attempt}/{job.max_attempts}
              </td>
              <td>{new Date(job.queued_at).toLocaleString()}</td>
              <td style={{ color: "var(--color-danger)" }}>{job.error_code ?? "—"}</td>
              <td>
                {job.status === "failed" && (
                  <Button variant="secondary" onClick={() => void handleRetry(job.id)}>
                    Retry
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {jobsQuery.data && (
        <p style={{ marginTop: "var(--space-3)", color: "var(--text-muted)" }}>
          {jobsQuery.data.total} total job(s)
        </p>
      )}
    </AdminLayout>
  );
}
