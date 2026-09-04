import { useQuery } from "@tanstack/react-query";

import { getWorkersOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

/**
 * Phase 7 Admin Portal Workers page: derived purely from `ProcessingJob`
 * rows already written by Phase 3's worker processes — no new
 * worker-registry table (narrow scope, matching the existing "avoid
 * building a hardware inventory platform" principle).
 */
export function AdminWorkersPage() {
  const workersQuery = useQuery({ queryKey: ["admin", "workers"], queryFn: getWorkersOverview });

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Workers</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Derived from processing job activity — a worker is considered
        "active" only while it currently holds a RUNNING job's lease.
      </p>
      <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-6)" }}>
        {workersQuery.data?.workers.map((w) => (
          <div
            key={w.role}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{w.role}</strong>
              <Badge tone={w.active_worker_ids.length > 0 ? "success" : "neutral"}>
                {w.active_worker_ids.length > 0 ? "active" : "idle"}
              </Badge>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              Job types: {w.job_types.join(", ")}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Running: {w.running_jobs} · Queued: {w.queued_jobs}
            </p>
            {w.active_worker_ids.length > 0 && (
              <p style={{ color: "var(--text-secondary)" }}>
                Active worker id(s): {w.active_worker_ids.join(", ")}
              </p>
            )}
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              Last activity:{" "}
              {w.last_activity_at ? new Date(w.last_activity_at).toLocaleString() : "none observed"}
            </p>
          </div>
        ))}
      </div>
    </AdminLayout>
  );
}
