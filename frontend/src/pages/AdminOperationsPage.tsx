import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createBackup,
  getModelStorageOverview,
  getOperationsMetrics,
  listBackups,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exp = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** exp).toFixed(1)} ${units[exp]}`;
}

const cardStyle: React.CSSProperties = {
  border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-4)",
};

/**
 * Phase 11 Admin Portal Operations page: real Worker/GPU/Queue metrics
 * (extends Phase 7's Workers/Jobs read-model with throughput aggregates),
 * Model Storage (the models volume specifically, distinct from Phase 7's
 * general conversation-media Storage page), and Backup (create/list —
 * restore is deliberately CLI-only, see backend/app/operations/backup_service.py's
 * module docstring for why: a destructive operation like restore should
 * never be one accidental click away, and this page never offers it).
 */
export function AdminOperationsPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [backupError, setBackupError] = useState<string | null>(null);
  const [backupBusy, setBackupBusy] = useState(false);

  const metricsQuery = useQuery({
    queryKey: ["admin", "operations", "metrics"],
    queryFn: getOperationsMetrics,
    refetchInterval: 15000,
  });
  const modelStorageQuery = useQuery({
    queryKey: ["admin", "operations", "model-storage"],
    queryFn: getModelStorageOverview,
  });
  const backupsQuery = useQuery({
    queryKey: ["admin", "operations", "backups"],
    queryFn: listBackups,
  });

  const canTriggerBackup = hasPermission("backup:trigger");
  const gpu = metricsQuery.data?.gpu;

  async function handleCreateBackup() {
    if (!csrfToken) return;
    setBackupBusy(true);
    setBackupError(null);
    try {
      await createBackup(csrfToken);
      await queryClient.invalidateQueries({ queryKey: ["admin", "operations", "backups"] });
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "Backup failed.");
    } finally {
      setBackupBusy(false);
    }
  }

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
        Operations
      </h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Real worker/GPU/queue metrics, model storage usage, and backups.
        Every number below is a real aggregate or filesystem/subprocess
        read — anything not reliably available renders as "not available",
        never a fabricated value. Retention cleanup lives on the{" "}
        <a href="/admin/retention">Retention</a> page.
      </p>

      <h2 style={{ marginTop: "var(--space-6)" }}>Worker throughput</h2>
      <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-3)" }}>
        {metricsQuery.data?.workers.map((w) => (
          <div key={w.role} style={cardStyle}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{w.role}</strong>
              <Badge tone={w.active_worker_ids.length > 0 ? "success" : "neutral"}>
                {w.active_worker_ids.length > 0 ? "active" : "idle"}
              </Badge>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              Running: {w.running_jobs} · Queued: {w.queued_jobs}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Succeeded (1h / 24h): {w.succeeded_last_1h} / {w.succeeded_last_24h} · Failed (24h):{" "}
              {w.failed_last_24h}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Avg duration (24h):{" "}
              {w.avg_duration_seconds_last_24h !== null
                ? `${w.avg_duration_seconds_last_24h.toFixed(1)}s (n=${w.sample_count_last_24h})`
                : "not available"}
            </p>
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: "var(--space-6)" }}>GPU</h2>
      <div style={cardStyle}>
        {gpu ? (
          gpu.cuda_available ? (
            <>
              <p>Device: {gpu.device_name ?? "unknown"}</p>
              <p>
                VRAM: {gpu.free_vram_mb ?? "?"} MB free of {gpu.total_vram_mb ?? "?"} MB
              </p>
              <p>
                Utilization:{" "}
                {gpu.utilization_percent !== null
                  ? `${gpu.utilization_percent}%`
                  : "not available (nvidia-smi not reachable)"}
              </p>
            </>
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>No CUDA-capable GPU detected.</p>
          )
        ) : (
          <p style={{ color: "var(--text-muted)" }}>Loading…</p>
        )}
      </div>

      <h2 style={{ marginTop: "var(--space-6)" }}>Queue depth by job type</h2>
      <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Job type</th>
            <th>Queued</th>
            <th>Running</th>
          </tr>
        </thead>
        <tbody>
          {metricsQuery.data?.queue.depth_by_job_type.map((row) => (
            <tr key={row.job_type} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{row.job_type}</td>
              <td>{row.queued}</td>
              <td>{row.running}</td>
            </tr>
          ))}
          {metricsQuery.data?.queue.depth_by_job_type.length === 0 && (
            <tr>
              <td colSpan={3} style={{ color: "var(--text-muted)" }}>
                No queued or running jobs.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 style={{ marginTop: "var(--space-6)" }}>Model storage</h2>
      <div style={cardStyle}>
        {modelStorageQuery.data && (
          <>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              {modelStorageQuery.data.model_volume_root}
            </p>
            <p>Total: {formatBytes(modelStorageQuery.data.total_bytes)}</p>
            <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                  <th>Model</th>
                  <th>Size</th>
                </tr>
              </thead>
              <tbody>
                {modelStorageQuery.data.models.map((m) => (
                  <tr key={m.name} style={{ borderBottom: "1px solid var(--border-default)" }}>
                    <td>{m.name}</td>
                    <td>{formatBytes(m.size_bytes)}</td>
                  </tr>
                ))}
                {modelStorageQuery.data.models.length === 0 && (
                  <tr>
                    <td colSpan={2} style={{ color: "var(--text-muted)" }}>
                      No installed models found under the model volume.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-6)" }}>
        <h2>Backups</h2>
        {canTriggerBackup && (
          <Button variant="primary" onClick={() => void handleCreateBackup()} disabled={backupBusy}>
            {backupBusy ? "Creating…" : "Create backup"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)" }}>
        A backup is a real PostgreSQL dump plus a media archive, written to
        the server's configured backup root. Restore is an operator-run CLI
        command only (<code>python -m app.cli.backup restore &lt;id&gt;</code>) —
        deliberately not available from this page. See{" "}
        <a href="https://github.com/ley338-gif/VocaDox/blob/main/docs/operations/disaster-recovery.md">
          the disaster recovery runbook
        </a>
        .
      </p>
      {backupError && <p style={{ color: "var(--status-error-text, crimson)" }}>{backupError}</p>}
      <table style={{ width: "100%", marginTop: "var(--space-3)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Started</th>
            <th>Status</th>
            <th>DB dump</th>
            <th>Media archive</th>
            <th>Files</th>
          </tr>
        </thead>
        <tbody>
          {backupsQuery.data?.map((b) => (
            <tr key={b.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{new Date(b.started_at).toLocaleString()}</td>
              <td>
                <Badge tone={b.status === "succeeded" ? "success" : b.status === "failed" ? "danger" : "neutral"}>
                  {b.status}
                </Badge>
              </td>
              <td>{b.database_dump_bytes !== null ? formatBytes(b.database_dump_bytes) : "—"}</td>
              <td>{b.media_archive_bytes !== null ? formatBytes(b.media_archive_bytes) : "—"}</td>
              <td>{b.media_file_count ?? "—"}</td>
            </tr>
          ))}
          {backupsQuery.data?.length === 0 && (
            <tr>
              <td colSpan={5} style={{ color: "var(--text-muted)" }}>
                No backups yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </AdminLayout>
  );
}
