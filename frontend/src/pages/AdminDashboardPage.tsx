import { useQuery } from "@tanstack/react-query";
import { Activity, Cpu, HardDrive } from "lucide-react";

import { getDashboard } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Card, StatCard } from "../design-system/Card";
import { ErrorState, Skeleton } from "../design-system/States";

/**
 * Phase 7 Admin Portal Dashboard (spec §49): real, live-checked component
 * health, real queue counts, a narrow hardware snapshot — never a
 * fabricated "Healthy" placeholder. Hard privacy rule: this page must
 * never render conversation/fact/transcript/document content — the
 * backend response (`GET /admin/dashboard`) structurally cannot carry any
 * (see `app.administration.schemas.DashboardResponse`), so there is
 * nothing here to accidentally leak.
 */
export function AdminDashboardPage() {
  const dashboardQuery = useQuery({ queryKey: ["admin", "dashboard"], queryFn: getDashboard });
  const dashboard = dashboardQuery.data;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Dashboard</h1>

      {dashboardQuery.isLoading && (
        <div style={{ marginTop: "var(--space-6)", display: "flex", gap: "var(--space-4)" }}>
          <Skeleton height="4rem" width="180px" />
          <Skeleton height="4rem" width="180px" />
          <Skeleton height="4rem" width="180px" />
        </div>
      )}

      {dashboardQuery.isError && (
        <div style={{ marginTop: "var(--space-6)" }}>
          <ErrorState message="Dashboard-Daten konnten nicht geladen werden." />
        </div>
      )}

      {dashboard && (
        <>
          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h3-size)", marginBottom: "var(--space-3)" }}>System health</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)" }}>
              {dashboard.components.map((c) => (
                <Card key={c.name} padded>
                  <div style={{ fontWeight: 600, marginBottom: "var(--space-1)" }}>{c.name.replace(/_/g, " ")}</div>
                  <Badge tone={c.healthy ? "success" : "danger"}>{c.healthy ? "healthy" : "unavailable"}</Badge>
                  {c.detail && (
                    <p style={{ color: "var(--text-secondary)", fontSize: "var(--font-caption-size)", marginTop: "var(--space-1)" }}>
                      {c.detail}
                    </p>
                  )}
                </Card>
              ))}
            </div>
          </section>

          <section style={{ marginTop: "var(--space-8)" }}>
            <h2 style={{ fontSize: "var(--font-h3-size)", marginBottom: "var(--space-3)" }}>Processing queue</h2>
            <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
              <StatCard label="Queued" value={dashboard.queue.queued} icon={<Activity size={18} aria-hidden="true" />} />
              <StatCard label="Running" value={dashboard.queue.running} icon={<Activity size={18} aria-hidden="true" />} />
              <StatCard label="Failed" value={dashboard.queue.failed} icon={<Activity size={18} aria-hidden="true" />} />
            </div>
          </section>

          <section style={{ marginTop: "var(--space-8)" }}>
            <h2 style={{ fontSize: "var(--font-h3-size)", marginBottom: "var(--space-3)" }}>Hardware</h2>
            <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
              <StatCard
                label="CPU cores"
                value={dashboard.hardware.cpu_count ?? "—"}
                icon={<Cpu size={18} aria-hidden="true" />}
              />
              <StatCard
                label="RAM"
                value={
                  dashboard.hardware.total_ram_mb !== null
                    ? `${Math.round(dashboard.hardware.total_ram_mb / 1024)} GB`
                    : "—"
                }
                icon={<HardDrive size={18} aria-hidden="true" />}
              />
              <StatCard
                label="CUDA"
                value={dashboard.hardware.cuda_available ? "verfügbar" : "nicht verfügbar"}
                hint={dashboard.hardware.cuda_available ? dashboard.hardware.gpu_device_name ?? undefined : undefined}
              />
              {dashboard.hardware.cuda_available && (
                <StatCard
                  label="VRAM frei"
                  value={`${dashboard.hardware.free_vram_mb ?? "?"} MB`}
                  hint={`von ${dashboard.hardware.total_vram_mb ?? "?"} MB`}
                />
              )}
            </div>
          </section>

          <p style={{ marginTop: "var(--space-8)", color: "var(--text-muted)" }}>
            VocaDox {dashboard.application_version}
          </p>
        </>
      )}
    </AdminLayout>
  );
}
