import { useQuery } from "@tanstack/react-query";

import { getWorkersOverview } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Card } from "../design-system/Card";
import { Skeleton } from "../design-system/States";

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
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Worker</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Abgeleitet aus der Verarbeitungsjob-Aktivität — ein Worker gilt nur als "aktiv", solange er
        gerade den Lease eines laufenden Jobs hält.
      </p>
      {workersQuery.isLoading && <Skeleton height="6rem" />}
      <div style={{ display: "grid", gap: "var(--space-4)" }}>
        {workersQuery.data?.workers.map((w) => (
          <Card key={w.role}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{w.role}</strong>
              <Badge tone={w.active_worker_ids.length > 0 ? "success" : "neutral"}>
                {w.active_worker_ids.length > 0 ? "aktiv" : "inaktiv"}
              </Badge>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              Job-Typen: {w.job_types.join(", ")}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Läuft: {w.running_jobs} · Wartend: {w.queued_jobs}
            </p>
            {w.active_worker_ids.length > 0 && (
              <p style={{ color: "var(--text-secondary)" }}>
                Aktive Worker-ID(s): {w.active_worker_ids.join(", ")}
              </p>
            )}
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              Letzte Aktivität:{" "}
              {w.last_activity_at ? new Date(w.last_activity_at).toLocaleString() : "keine beobachtet"}
            </p>
          </Card>
        ))}
      </div>
    </AdminLayout>
  );
}
