import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type ServiceAccountCreated,
  createServiceAccount,
  listAvailableScopes,
  listOrganizations,
  listServiceAccounts,
  listUsers,
  revokeServiceAccount,
  rotateServiceAccount,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { Checkbox, Select, TextInput } from "../design-system/FormControls";

/**
 * Phase 10 Admin Portal: Service Accounts (spec §54). Follows the exact
 * Phase 7 admin-CRUD-page pattern (see AdminRetentionPage.tsx) plus the
 * one thing genuinely new to this domain: a raw API key is only ever
 * available in the create/rotate response body, once — this page is the
 * only place it's ever displayed, and it is never persisted client-side
 * beyond the component's own state (lost on refresh, by design).
 */
export function AdminServiceAccountsPage() {
  const { csrfToken, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canWrite = hasPermission("service-account:write");

  const [showCreate, setShowCreate] = useState(false);
  const [revealedKey, setRevealedKey] = useState<ServiceAccountCreated | null>(null);
  const [form, setForm] = useState({
    name: "",
    description: "",
    organization_id: "",
    owner_user_id: "",
    scopes: [] as string[],
  });

  const accountsQuery = useQuery({ queryKey: ["admin", "service-accounts"], queryFn: listServiceAccounts });
  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers });
  const scopesQuery = useQuery({ queryKey: ["admin", "service-account-scopes"], queryFn: listAvailableScopes });

  function toggleScope(scope: string) {
    setForm((f) => ({
      ...f,
      scopes: f.scopes.includes(scope) ? f.scopes.filter((s) => s !== scope) : [...f.scopes, scope],
    }));
  }

  async function handleCreate() {
    if (!csrfToken || !form.name.trim() || !form.organization_id) return;
    const created = await createServiceAccount(
      {
        name: form.name,
        description: form.description || null,
        organization_id: form.organization_id,
        scopes: form.scopes,
        owner_user_id: form.owner_user_id || null,
      },
      csrfToken
    );
    setRevealedKey(created);
    setForm({ name: "", description: "", organization_id: "", owner_user_id: "", scopes: [] });
    setShowCreate(false);
    await queryClient.invalidateQueries({ queryKey: ["admin", "service-accounts"] });
  }

  async function handleRotate(accountId: string) {
    if (!csrfToken) return;
    if (!confirm("Rotate this service account's secret? The old API key will stop working immediately.")) return;
    const rotated = await rotateServiceAccount(accountId, csrfToken);
    setRevealedKey(rotated);
    await queryClient.invalidateQueries({ queryKey: ["admin", "service-accounts"] });
  }

  async function handleRevoke(accountId: string) {
    if (!csrfToken) return;
    if (!confirm("Revoke this service account? It will immediately stop authenticating.")) return;
    await revokeServiceAccount(accountId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "service-accounts"] });
  }

  const orgName = (id: string) => orgsQuery.data?.find((o) => o.id === id)?.name ?? id;
  const userName = (id: string | null) =>
    id ? (usersQuery.data?.find((u) => u.id === id)?.display_name ?? id) : "—";

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
          Service Accounts
        </h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? "Cancel" : "New service account"}
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)" }}>
        Non-human API clients, always scoped to one organization. Scopes are
        the same permission codes RBAC uses elsewhere. A service account's
        API key is shown in full only once, immediately after creation or
        rotation — VocaDox never stores or displays it again.
      </p>

      {revealedKey && (
        <div
          style={{
            border: "1px solid var(--color-warning-border, orange)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            background: "var(--surface-warning, rgba(255,180,0,0.08))",
          }}
        >
          <strong>API key for "{revealedKey.name}" — copy it now, it will not be shown again:</strong>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
            <code
              style={{
                flex: 1,
                padding: "var(--space-2)",
                background: "var(--surface-secondary)",
                borderRadius: "var(--radius-sm)",
                overflowWrap: "anywhere",
              }}
            >
              {revealedKey.api_key}
            </code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(revealedKey.api_key)}>
              Copy
            </Button>
            <Button variant="secondary" onClick={() => setRevealedKey(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {showCreate && (
        <div
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            display: "grid",
            gap: "var(--space-3)",
            maxWidth: "480px",
          }}
        >
          <TextInput
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextInput
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <Select
            value={form.organization_id}
            onChange={(e) => setForm({ ...form, organization_id: e.target.value })}
          >
            <option value="">Select organization…</option>
            {orgsQuery.data?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
          <Select
            value={form.owner_user_id}
            onChange={(e) => setForm({ ...form, owner_user_id: e.target.value })}
          >
            <option value="">No owner (read-only scopes only)</option>
            {usersQuery.data?.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name} ({u.username})
              </option>
            ))}
          </Select>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "var(--font-caption-size)" }}>
            Owner: the human user this account's writes (create/compose/approve) are
            attributed to. Required for any write scope.
          </p>
          <div>
            {scopesQuery.data?.scopes.map((scope) => (
              <label key={scope} style={{ display: "block" }}>
                <Checkbox checked={form.scopes.includes(scope)} onChange={() => toggleScope(scope)} /> {scope}
              </label>
            ))}
          </div>
          <Button variant="primary" onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Name</th>
            <th>Organization</th>
            <th>Key prefix</th>
            <th>Scopes</th>
            <th>Owner</th>
            <th>Status</th>
            <th>Last used</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {accountsQuery.data?.map((account) => (
            <tr key={account.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{account.name}</td>
              <td>{orgName(account.organization_id)}</td>
              <td>
                <code>{account.key_prefix}</code>
              </td>
              <td style={{ fontSize: "var(--font-caption-size)" }}>{account.scopes.join(", ") || "—"}</td>
              <td>{userName(account.owner_user_id)}</td>
              <td>
                <Badge tone={account.is_active ? "success" : "neutral"}>
                  {account.is_active ? "active" : "revoked"}
                </Badge>
              </td>
              <td>{account.last_used_at ? new Date(account.last_used_at).toLocaleString() : "never"}</td>
              <td style={{ display: "flex", gap: "var(--space-2)" }}>
                {canWrite && account.is_active && (
                  <>
                    <Button variant="secondary" onClick={() => void handleRotate(account.id)}>
                      Rotate
                    </Button>
                    <Button variant="destructive" onClick={() => void handleRevoke(account.id)}>
                      Revoke
                    </Button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </AdminLayout>
  );
}
