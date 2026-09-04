import { useQuery } from "@tanstack/react-query";

import { getStorageUsage } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exp = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** exp).toFixed(1)} ${units[exp]}`;
}

/**
 * Phase 7 Admin Portal Storage page: real disk usage figures (an actual
 * recursive scan of the media storage root + the model volume, plus real
 * `shutil.disk_usage` filesystem totals) — never fabricated.
 */
export function AdminStoragePage() {
  const storageQuery = useQuery({ queryKey: ["admin", "storage"], queryFn: getStorageUsage });
  const storage = storageQuery.data;

  return (
    <AdminLayout>
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Storage</h1>
      {storage && (
        <div style={{ display: "grid", gap: "var(--space-6)", marginTop: "var(--space-6)" }}>
          <div
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}
          >
            <strong>Conversation media</strong>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              {storage.media_storage_root}
            </p>
            <p>Used: {formatBytes(storage.media_used_bytes)}</p>
            <p style={{ color: "var(--text-secondary)" }}>
              Disk: {formatBytes(storage.media_disk_free_bytes)} free of{" "}
              {formatBytes(storage.media_disk_total_bytes)}
            </p>
          </div>
          <div
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}
          >
            <strong>Model volume</strong>
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
              {storage.model_volume_root}
            </p>
            <p>Used: {formatBytes(storage.model_volume_used_bytes)}</p>
            <p style={{ color: "var(--text-secondary)" }}>
              Disk: {formatBytes(storage.model_volume_disk_free_bytes)} free of{" "}
              {formatBytes(storage.model_volume_disk_total_bytes)}
            </p>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
