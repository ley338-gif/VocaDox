import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createBackup,
  getModelStorageOverview,
  getOperationsMetrics,
  listBackups,
  type BackupRecord,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Card } from "../design-system/Card";
import { ErrorState, Skeleton } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exp = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** exp).toFixed(1)} ${units[exp]}`;
}

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
      setBackupError(err instanceof Error ? err.message : "Backup fehlgeschlagen.");
    } finally {
      setBackupBusy(false);
    }
  }

  const backupColumns: DataTableColumn<BackupRecord>[] = [
    { key: "started", header: "Gestartet", render: (b) => new Date(b.started_at).toLocaleString() },
    {
      key: "status",
      header: "Status",
      render: (b) => (
        <Badge tone={b.status === "succeeded" ? "success" : b.status === "failed" ? "danger" : "neutral"}>
          {b.status}
        </Badge>
      ),
    },
    { key: "db", header: "DB-Dump", render: (b) => (b.database_dump_bytes !== null ? formatBytes(b.database_dump_bytes) : "—") },
    { key: "media", header: "Medien-Archiv", render: (b) => (b.media_archive_bytes !== null ? formatBytes(b.media_archive_bytes) : "—") },
    { key: "files", header: "Dateien", render: (b) => b.media_file_count ?? "—" },
  ];

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Betrieb</h1>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        Echte Worker-/GPU-/Queue-Metriken, Modellspeichernutzung und Backups. Jede Zahl unten ist ein
        echter Aggregat- oder Dateisystem-/Subprozess-Wert — nicht zuverlässig Verfügbares wird als
        "nicht verfügbar" angezeigt, nie als erfundener Wert. Retention-Cleanup befindet sich auf der{" "}
        <a href="/admin/retention">Aufbewahrung</a>-Seite.
      </p>

      <h2 style={{ marginBottom: "var(--space-3)" }}>Worker-Durchsatz</h2>
      {metricsQuery.isLoading && <Skeleton height="6rem" />}
      <div style={{ display: "grid", gap: "var(--space-4)" }}>
        {metricsQuery.data?.workers.map((w) => (
          <Card key={w.role}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{w.role}</strong>
              <Badge tone={w.active_worker_ids.length > 0 ? "success" : "neutral"}>
                {w.active_worker_ids.length > 0 ? "aktiv" : "inaktiv"}
              </Badge>
            </div>
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
              Läuft: {w.running_jobs} · Wartend: {w.queued_jobs}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Erfolgreich (1h / 24h): {w.succeeded_last_1h} / {w.succeeded_last_24h} · Fehlgeschlagen
              (24h): {w.failed_last_24h}
            </p>
            <p style={{ color: "var(--text-secondary)" }}>
              Ø Dauer (24h):{" "}
              {w.avg_duration_seconds_last_24h !== null
                ? `${w.avg_duration_seconds_last_24h.toFixed(1)}s (n=${w.sample_count_last_24h})`
                : "nicht verfügbar"}
            </p>
          </Card>
        ))}
      </div>

      <h2 style={{ marginTop: "var(--space-6)", marginBottom: "var(--space-3)" }}>GPU</h2>
      <Card>
        {gpu ? (
          gpu.cuda_available ? (
            <>
              <p>Gerät: {gpu.device_name ?? "unbekannt"}</p>
              <p>
                VRAM: {gpu.free_vram_mb ?? "?"} MB frei von {gpu.total_vram_mb ?? "?"} MB
              </p>
              <p>
                Auslastung:{" "}
                {gpu.utilization_percent !== null
                  ? `${gpu.utilization_percent}%`
                  : "nicht verfügbar (nvidia-smi nicht erreichbar)"}
              </p>
            </>
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>Keine CUDA-fähige GPU erkannt.</p>
          )
        ) : (
          <p style={{ color: "var(--text-muted)" }}>Lädt…</p>
        )}
      </Card>

      <h2 style={{ marginTop: "var(--space-6)", marginBottom: "var(--space-3)" }}>Queue-Tiefe nach Job-Typ</h2>
      <DataTable
        columns={[
          { key: "job_type", header: "Job-Typ", render: (row) => row.job_type },
          { key: "queued", header: "Wartend", render: (row) => row.queued },
          { key: "running", header: "Läuft", render: (row) => row.running },
        ]}
        rows={metricsQuery.data?.queue.depth_by_job_type ?? []}
        keyExtractor={(row) => row.job_type}
        empty={<p style={{ color: "var(--text-muted)" }}>Keine wartenden oder laufenden Jobs.</p>}
      />

      <h2 style={{ marginTop: "var(--space-6)", marginBottom: "var(--space-3)" }}>Modellspeicher</h2>
      <Card>
        {modelStorageQuery.data && (
          <>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              {modelStorageQuery.data.model_volume_root}
            </p>
            <p>Gesamt: {formatBytes(modelStorageQuery.data.total_bytes)}</p>
            <div style={{ marginTop: "var(--space-3)" }}>
              <DataTable
                columns={[
                  { key: "name", header: "Modell", render: (m) => m.name },
                  { key: "size", header: "Größe", render: (m) => formatBytes(m.size_bytes) },
                ]}
                rows={modelStorageQuery.data.models}
                keyExtractor={(m) => m.name}
                empty={<p style={{ color: "var(--text-muted)" }}>Keine installierten Modelle im Modell-Volume gefunden.</p>}
              />
            </div>
          </>
        )}
      </Card>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-6)", marginBottom: "var(--space-2)" }}>
        <h2>Backups</h2>
        {canTriggerBackup && (
          <Button variant="primary" onClick={() => void handleCreateBackup()} disabled={backupBusy}>
            {backupBusy ? "Wird erstellt…" : "Backup erstellen"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)" }}>
        Ein Backup ist ein echter PostgreSQL-Dump plus ein Medienarchiv, geschrieben in das
        konfigurierte Backup-Verzeichnis des Servers. Die Wiederherstellung erfolgt ausschließlich
        über einen vom Operator ausgeführten CLI-Befehl (
        <code>python -m app.cli.backup restore &lt;id&gt;</code>) — absichtlich nicht von dieser
        Seite aus verfügbar. Siehe{" "}
        <a href="https://github.com/ley338-gif/VocaDox/blob/main/docs/operations/disaster-recovery.md">
          das Disaster-Recovery-Runbook
        </a>
        .
      </p>
      {backupError && (
        <div style={{ margin: "var(--space-3) 0" }}>
          <ErrorState message={backupError} />
        </div>
      )}
      <div style={{ marginTop: "var(--space-3)" }}>
        <DataTable
          columns={backupColumns}
          rows={backupsQuery.data ?? []}
          keyExtractor={(b) => b.id}
          empty={<p style={{ color: "var(--text-muted)" }}>Noch keine Backups.</p>}
        />
      </div>
    </AdminLayout>
  );
}
