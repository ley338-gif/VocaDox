import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createRetentionPolicy, listRetentionPolicies, updateRetentionPolicy } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Checkbox, TextInput } from "../design-system/FormControls";

/**
 * Phase 7 Admin Portal Retention page: the `retention_policies` data
 * model has existed since Phase 2 with no admin UI until now. This page
 * manages the policy rows only — no automated enforcement/cleanup
 * scheduler runs yet (that's Phase 11's "Retention Cleanup" scope).
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
  });

  const policiesQuery = useQuery({
    queryKey: ["admin", "retention-policies"],
    queryFn: listRetentionPolicies,
  });
  const canWrite = hasPermission("retention:write");

  async function handleCreate() {
    if (!csrfToken || !form.name.trim()) return;
    await createRetentionPolicy(
      {
        name: form.name,
        retention_days: form.retention_days ? Number(form.retention_days) : null,
        delete_source_media: form.delete_source_media,
        delete_derived_media: form.delete_derived_media,
        active: true,
      },
      csrfToken
    );
    setForm({ name: "", retention_days: "", delete_source_media: false, delete_derived_media: false });
    setShowCreate(false);
    await queryClient.invalidateQueries({ queryKey: ["admin", "retention-policies"] });
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
    </AdminLayout>
  );
}
