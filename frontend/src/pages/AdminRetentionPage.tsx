import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createRetentionPolicy,
  listRetentionCleanupRuns,
  listRetentionPolicies,
  runRetentionCleanup,
  updateRetentionPolicy,
  type RetentionCleanupRun,
  type RetentionPolicy,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { FormField } from "../design-system/FormField";
import { Checkbox, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 7 Admin Portal Retention page: the `retention_policies` data
 * model has existed since Phase 2 with no admin UI until now.
 *
 * Phase 11 adds the real Retention Cleanup Worker's admin surface below
 * the policy table: a dry-run-by-default trigger and a run history. Real
 * physical deletion only happens when an admin explicitly checks "Actually
 * delete" — see backend/app/operations/retention_service.py for the full
 * set of safety rules this enforces server-side (this checkbox is a UX
 * safeguard on top of, never instead of, the server defaulting to
 * dry_run=true). Redesign note: this destructive-action UX (checkbox +
 * destructive-variant button + explicit "irreversible" label) is kept
 * byte-for-byte identical in behavior — only surrounding chrome changed.
 */
export function AdminRetentionPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: "",
    retention_days: "",
    delete_source_media: false,
    delete_derived_media: false,
    delete_transcript: false,
  });
  const [executeCleanup, setExecuteCleanup] = useState(false);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupError, setCleanupError] = useState<string | null>(null);

  const policiesQuery = useQuery({
    queryKey: ["admin", "retention-policies"],
    queryFn: listRetentionPolicies,
  });
  const canWrite = hasPermission("retention:write");
  const canRead = hasPermission("retention-cleanup:read");
  const canTrigger = hasPermission("retention-cleanup:trigger");

  const cleanupRunsQuery = useQuery({
    queryKey: ["admin", "retention-cleanup", "runs"],
    queryFn: listRetentionCleanupRuns,
    enabled: canRead,
  });

  async function handleCreate() {
    if (!csrfToken || !form.name.trim()) return;
    await createRetentionPolicy(
      {
        name: form.name,
        retention_days: form.retention_days ? Number(form.retention_days) : null,
        delete_source_media: form.delete_source_media,
        delete_derived_media: form.delete_derived_media,
        delete_transcript: form.delete_transcript,
        active: true,
      },
      csrfToken
    );
    setForm({
      name: "",
      retention_days: "",
      delete_source_media: false,
      delete_derived_media: false,
      delete_transcript: false,
    });
    setShowCreate(false);
    await queryClient.invalidateQueries({ queryKey: ["admin", "retention-policies"] });
  }

  async function handleRunCleanup() {
    if (!csrfToken) return;
    setCleanupBusy(true);
    setCleanupError(null);
    try {
      await runRetentionCleanup(!executeCleanup, csrfToken);
      setExecuteCleanup(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "retention-cleanup", "runs"] });
    } catch (err) {
      setCleanupError(err instanceof Error ? err.message : "Retention-Cleanup-Lauf fehlgeschlagen.");
    } finally {
      setCleanupBusy(false);
    }
  }

  async function handleToggleActive(policyId: string, active: boolean) {
    if (!csrfToken) return;
    await updateRetentionPolicy(policyId, { active: !active }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "retention-policies"] });
  }

  const policyColumns: DataTableColumn<RetentionPolicy>[] = [
    { key: "name", header: "Name", render: (p) => p.name },
    { key: "retention", header: "Aufbewahrung", render: (p) => (p.retention_days !== null ? `${p.retention_days} Tage` : "unbegrenzt") },
    { key: "source", header: "Quelle löschen", render: (p) => (p.delete_source_media ? "ja" : "nein") },
    { key: "derived", header: "Abgeleitet löschen", render: (p) => (p.delete_derived_media ? "ja" : "nein") },
    { key: "transcript", header: "Transkript löschen", render: (p) => (p.delete_transcript ? "ja" : "nein") },
    {
      key: "status",
      header: "Status",
      render: (p) => <Badge tone={p.active ? "success" : "neutral"}>{p.active ? "aktiv" : "inaktiv"}</Badge>,
    },
  ];

  const runColumns: DataTableColumn<RetentionCleanupRun>[] = [
    { key: "started", header: "Gestartet", render: (r) => new Date(r.started_at).toLocaleString() },
    { key: "mode", header: "Modus", render: (r) => <Badge tone={r.dry_run ? "info" : "warning"}>{r.dry_run ? "Testlauf" : "ausgeführt"}</Badge> },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <Badge tone={r.status === "succeeded" ? "success" : r.status === "failed" ? "danger" : "neutral"}>
          {r.status}
        </Badge>
      ),
    },
    { key: "evaluated", header: "Geprüft", render: (r) => r.conversations_evaluated },
    { key: "deleted", header: "Gelöscht", render: (r) => r.items_deleted },
    { key: "freed", header: "Freigegeben", render: (r) => `${r.bytes_freed.toLocaleString()} B` },
  ];

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Aufbewahrung</h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            Neue Richtlinie
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginBottom: "var(--space-4)" }}>
        Aufbewahrungsrichtlinien können Gesprächen zugewiesen werden (über ein Verarbeitungsprofil
        oder direkt). Es läuft noch keine automatisierte Bereinigung gegen sie — die Durchsetzung
        erfolgt unten; diese Seite verwaltet nur die Richtliniendefinitionen.
      </p>

      <DataTable
        columns={policyColumns}
        rows={policiesQuery.data ?? []}
        keyExtractor={(p) => p.id}
        loading={policiesQuery.isLoading}
        rowActions={(p) =>
          canWrite ? (
            <Button variant="secondary" onClick={() => void handleToggleActive(p.id, p.active)}>
              {p.active ? "Deaktivieren" : "Aktivieren"}
            </Button>
          ) : null
        }
      />

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Neue Aufbewahrungsrichtlinie">
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Richtlinienname" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="Aufbewahrungstage" hint="Leer lassen = unbegrenzt">
            <TextInput value={form.retention_days} onChange={(e) => setForm({ ...form, retention_days: e.target.value })} />
          </FormField>
          <label>
            <Checkbox
              checked={form.delete_source_media}
              onChange={(e) => setForm({ ...form, delete_source_media: e.target.checked })}
            />{" "}
            Quellmedien bei Ablauf löschen
          </label>
          <label>
            <Checkbox
              checked={form.delete_derived_media}
              onChange={(e) => setForm({ ...form, delete_derived_media: e.target.checked })}
            />{" "}
            Abgeleitete Medien bei Ablauf löschen
          </label>
          <label>
            <Checkbox
              checked={form.delete_transcript}
              onChange={(e) => setForm({ ...form, delete_transcript: e.target.checked })}
            />{" "}
            Transkript bei Ablauf löschen
          </label>
          <Button variant="primary" onClick={() => void handleCreate()}>
            Erstellen
          </Button>
        </div>
      </Modal>

      {canRead && (
        <>
          <h2 style={{ marginTop: "var(--space-8)", marginBottom: "var(--space-2)" }}>Retention-Cleanup</h2>
          <p style={{ color: "var(--text-secondary)" }}>
            Prüft jede aktive Richtlinie oben gegen ihre zugewiesenen Gespräche und führt, sobald das
            Alter eines Gesprächs den Schwellenwert der Richtlinie überschreitet, eine echte
            physische Löschung durch (nie nur ein Soft-Delete-Flag). Standardmäßig ein sicherer
            Testlauf, der genau protokolliert, was gelöscht würde, ohne etwas zu verändern.
          </p>
          {canTrigger && (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
              <label>
                <Checkbox
                  checked={executeCleanup}
                  onChange={(e) => setExecuteCleanup(e.target.checked)}
                />{" "}
                Tatsächlich löschen (deaktivieren für einen sicheren Testlauf)
              </label>
              <Button
                variant={executeCleanup ? "destructive" : "primary"}
                onClick={() => void handleRunCleanup()}
                disabled={cleanupBusy}
              >
                {cleanupBusy ? "Läuft…" : executeCleanup ? "Cleanup ausführen (unumkehrbar)" : "Testlauf starten"}
              </Button>
            </div>
          )}
          {cleanupError && (
            <div style={{ marginTop: "var(--space-3)" }}>
              <ErrorState message={cleanupError} />
            </div>
          )}

          <div style={{ marginTop: "var(--space-4)" }}>
            <DataTable
              columns={runColumns}
              rows={cleanupRunsQuery.data ?? []}
              keyExtractor={(r) => r.id}
              empty={<p style={{ color: "var(--text-muted)" }}>Noch keine Retention-Cleanup-Läufe.</p>}
            />
          </div>
        </>
      )}
    </AdminLayout>
  );
}
