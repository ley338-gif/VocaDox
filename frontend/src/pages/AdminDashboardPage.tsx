import { useQuery } from "@tanstack/react-query";

import { getDashboard } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";

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
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Dashboard
      </h1>
      {dashboard && (
        <>
          <section style={{ marginTop: "var(--space-6)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)" }}>System health</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
              {dashboard.components.map((c) => (
                <div
                  key={c.name}
                  style={{
                    border: "1px solid var(--border-default)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-3) var(--space-4)",
                    minWidth: "160px",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{c.name.replace(/_/g, " ")}</div>
                  <Badge tone={c.healthy ? "success" : "danger"}>
                    {c.healthy ? "healthy" : "unavailable"}
                  </Badge>
                  {c.detail && (
                    <p style={{ color: "var(--text-secondary)", fontSize: "var(--font-caption-size)" }}>
                      {c.detail}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section style={{ marginTop: "var(--space-8)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)" }}>Processing queue</h2>
            <div style={{ display: "flex", gap: "var(--space-6)", marginTop: "var(--space-3)" }}>
              <div>Queued: <strong>{dashboard.queue.queued}</strong></div>
              <div>Running: <strong>{dashboard.queue.running}</strong></div>
              <div>Failed: <strong>{dashboard.queue.failed}</strong></div>
            </div>
          </section>

          <section style={{ marginTop: "var(--space-8)" }}>
            <h2 style={{ fontSize: "var(--font-h2-size)" }}>Hardware</h2>
            <ul style={{ color: "var(--text-secondary)", marginTop: "var(--space-3)" }}>
              <li>CPU cores: {dashboard.hardware.cpu_count ?? "not available"}</li>
              <li>
                RAM:{" "}
                {dashboard.hardware.total_ram_mb !== null
                  ? `${Math.round(dashboard.hardware.total_ram_mb / 1024)} GB`
                  : "not available"}
              </li>
              <li>CUDA available: {dashboard.hardware.cuda_available ? "yes" : "no"}</li>
              {dashboard.hardware.cuda_available && (
                <>
                  <li>GPU: {dashboard.hardware.gpu_device_name ?? "unknown"}</li>
                  <li>
                    VRAM: {dashboard.hardware.free_vram_mb ?? "?"} MB free /{" "}
                    {dashboard.hardware.total_vram_mb ?? "?"} MB total
                  </li>
                </>
              )}
            </ul>
          </section>

          <p style={{ marginTop: "var(--space-8)", color: "var(--text-muted)" }}>
            VocaDox {dashboard.application_version}
          </p>
        </>
      )}
    </AdminLayout>
  );
}
