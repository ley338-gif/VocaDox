import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createRetentionPolicy,
  listRetentionCleanupRuns,
  listRetentionPolicies,
  runRetentionCleanup,
  updateRetentionPolicy,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Checkbox, TextInput } from "../design-system/FormControls";

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
 * dry_run=true).
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
      setCleanupError(err instanceof Error ? err.message : "Retention cleanup run failed.");
    } finally {
      setCleanupBusy(false);
    }
  }

  async function handleToggleActive(policyId: string, active: boolean) {
    if (!csrfToken) return;
    await updateRetentionPolicy(policyId, { active: !active }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "retention-policies"] });
  }

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
          Retention
        </h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? "Cancel" : "New policy"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Retention policies can be assigned to conversations (via a Processing
        Profile or directly). No automated cleanup runs against them yet —
        enforcement is a later phase; this page manages the policy
        definitions only.
      </p>

      {showCreate && (
        <div
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            display: "grid",
            gap: "var(--space-3)",
            maxWidth: "420px",
          }}
        >
          <TextInput
            placeholder="Policy name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextInput
            placeholder="Retention days (blank = indefinite)"
            value={form.retention_days}
            onChange={(e) => setForm({ ...form, retention_days: e.target.value })}
          />
          <label>
            <Checkbox
              checked={form.delete_source_media}
              onChange={(e) => setForm({ ...form, delete_source_media: e.target.checked })}
            />{" "}
            Delete source media on expiry
          </label>
          <label>
            <Checkbox
              checked={form.delete_derived_media}
              onChange={(e) => setForm({ ...form, delete_derived_media: e.target.checked })}
            />{" "}
            Delete derived media on expiry
          </label>
          <label>
            <Checkbox
              checked={form.delete_transcript}
              onChange={(e) => setForm({ ...form, delete_transcript: e.target.checked })}
            />{" "}
            Delete transcript on expiry
          </label>
          <Button variant="primary" onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Name</th>
            <th>Retention</th>
            <th>Delete source</th>
            <th>Delete derived</th>
            <th>Delete transcript</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {policiesQuery.data?.map((policy) => (
            <tr key={policy.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{policy.name}</td>
              <td>{policy.retention_days !== null ? `${policy.retention_days} days` : "indefinite"}</td>
              <td>{policy.delete_source_media ? "yes" : "no"}</td>
              <td>{policy.delete_derived_media ? "yes" : "no"}</td>
              <td>{policy.delete_transcript ? "yes" : "no"}</td>
              <td>
                <Badge tone={policy.active ? "success" : "neutral"}>
                  {policy.active ? "active" : "inactive"}
                </Badge>
              </td>
              <td>
                {canWrite && (
                  <Button
                    variant="secondary"
                    onClick={() => void handleToggleActive(policy.id, policy.active)}
                  >
                    {policy.active ? "Deactivate" : "Activate"}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {canRead && (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: "var(--space-8)",
            }}
          >
            <h2>Retention cleanup</h2>
          </div>
          <p style={{ color: "var(--text-secondary)" }}>
            Evaluates every active policy above against its assigned
            conversations and, once a conversation's age passes the
            policy's threshold, performs real physical deletion (never a
            soft-delete flag alone). Defaults to a safe dry run that
            records exactly what would be deleted without touching
            anything.
          </p>
          {canTrigger && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                marginTop: "var(--space-3)",
              }}
            >
              <label>
                <Checkbox
                  checked={executeCleanup}
                  onChange={(e) => setExecuteCleanup(e.target.checked)}
                />{" "}
                Actually delete (uncheck for a safe dry run)
              </label>
              <Button
                variant={executeCleanup ? "destructive" : "primary"}
                onClick={() => void handleRunCleanup()}
                disabled={cleanupBusy}
              >
                {cleanupBusy ? "Running…" : executeCleanup ? "Run cleanup (irreversible)" : "Run dry run"}
              </Button>
            </div>
          )}
          {cleanupError && <p style={{ color: "var(--status-error-text, crimson)" }}>{cleanupError}</p>}

          <table style={{ width: "100%", marginTop: "var(--space-4)", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                <th>Started</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Evaluated</th>
                <th>Deleted</th>
                <th>Bytes freed</th>
              </tr>
            </thead>
            <tbody>
              {cleanupRunsQuery.data?.map((run) => (
                <tr key={run.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
                  <td>{new Date(run.started_at).toLocaleString()}</td>
                  <td>
                    <Badge tone={run.dry_run ? "info" : "warning"}>
                      {run.dry_run ? "dry run" : "executed"}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={run.status === "succeeded" ? "success" : run.status === "failed" ? "danger" : "neutral"}>
                      {run.status}
                    </Badge>
                  </td>
                  <td>{run.conversations_evaluated}</td>
                  <td>{run.items_deleted}</td>
                  <td>{run.bytes_freed.toLocaleString()} B</td>
                </tr>
              ))}
              {cleanupRunsQuery.data?.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ color: "var(--text-muted)" }}>
                    No retention cleanup runs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </AdminLayout>
  );
}
