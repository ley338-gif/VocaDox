import { useQuery } from "@tanstack/react-query";
import { HardDrive } from "lucide-react";

import { getStorageUsage } from "../api/admin";
import { AdminLayout } from "../components/AdminLayout";
import { Card, StatCard } from "../design-system/Card";
import { Skeleton } from "../design-system/States";

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
      <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)", marginBottom: "var(--space-6)" }}>
        Speicher
      </h1>
      {storageQuery.isLoading && <Skeleton height="6rem" />}
      {storage && (
        <div style={{ display: "grid", gap: "var(--space-4)", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          <Card title="Gesprächsmedien">
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)", marginBottom: "var(--space-3)" }}>
              {storage.media_storage_root}
            </p>
            <StatCard label="Belegt" value={formatBytes(storage.media_used_bytes)} icon={<HardDrive size={18} aria-hidden="true" />} />
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-3)" }}>
              Datenträger: {formatBytes(storage.media_disk_free_bytes)} frei von{" "}
              {formatBytes(storage.media_disk_total_bytes)}
            </p>
          </Card>
          <Card title="Modell-Volume">
            <p style={{ color: "var(--text-muted)", fontSize: "var(--font-caption-size)", marginBottom: "var(--space-3)" }}>
              {storage.model_volume_root}
            </p>
            <StatCard label="Belegt" value={formatBytes(storage.model_volume_used_bytes)} icon={<HardDrive size={18} aria-hidden="true" />} />
            <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-3)" }}>
              Datenträger: {formatBytes(storage.model_volume_disk_free_bytes)} frei von{" "}
              {formatBytes(storage.model_volume_disk_total_bytes)}
            </p>
          </Card>
        </div>
      )}
    </AdminLayout>
  );
}
