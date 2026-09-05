import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type ServiceAccount,
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
import { Card } from "../design-system/Card";
import { FormField } from "../design-system/FormField";
import { Checkbox, Select, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { DataTable, type DataTableColumn } from "../design-system/Table";

/**
 * Phase 10 Admin Portal: Service Accounts (spec §54). Follows the exact
 * Phase 7 admin-CRUD-page pattern (see AdminRetentionPage.tsx) plus the
 * one thing genuinely new to this domain: a raw API key is only ever
 * available in the create/rotate response body, once — this page is the
 * only place it's ever displayed, and it is never persisted client-side
 * beyond the component's own state (lost on refresh, by design). Kept as
 * a prominent inline banner (not a Modal) so it can't be accidentally
 * dismissed by an outside click before the key is copied.
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
    if (!confirm("Diesen Service-Account-Schlüssel rotieren? Der alte API-Key funktioniert sofort nicht mehr.")) return;
    const rotated = await rotateServiceAccount(accountId, csrfToken);
    setRevealedKey(rotated);
    await queryClient.invalidateQueries({ queryKey: ["admin", "service-accounts"] });
  }

  async function handleRevoke(accountId: string) {
    if (!csrfToken) return;
    if (!confirm("Diesen Service Account widerrufen? Die Authentifizierung wird sofort ungültig.")) return;
    await revokeServiceAccount(accountId, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "service-accounts"] });
  }

  const orgName = (id: string) => orgsQuery.data?.find((o) => o.id === id)?.name ?? id;
  const userName = (id: string | null) =>
    id ? (usersQuery.data?.find((u) => u.id === id)?.display_name ?? id) : "—";

  const columns: DataTableColumn<ServiceAccount>[] = [
    { key: "name", header: "Name", render: (a) => a.name },
    { key: "org", header: "Organisation", render: (a) => orgName(a.organization_id) },
    { key: "prefix", header: "Key-Präfix", render: (a) => <code>{a.key_prefix}</code> },
    { key: "scopes", header: "Scopes", render: (a) => <span style={{ fontSize: "var(--font-caption-size)" }}>{a.scopes.join(", ") || "—"}</span> },
    { key: "owner", header: "Owner", render: (a) => userName(a.owner_user_id) },
    {
      key: "status",
      header: "Status",
      render: (a) => <Badge tone={a.is_active ? "success" : "neutral"}>{a.is_active ? "aktiv" : "widerrufen"}</Badge>,
    },
    { key: "last_used", header: "Zuletzt verwendet", render: (a) => (a.last_used_at ? new Date(a.last_used_at).toLocaleString() : "nie") },
  ];

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
          Service Accounts
        </h1>
        {canWrite && (
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            Neuer Service Account
          </Button>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-4)", marginBottom: "var(--space-4)" }}>
        Nicht-menschliche API-Clients, immer genau einer Organisation zugeordnet. Scopes sind
        dieselben Berechtigungscodes, die RBAC überall sonst verwendet. Der API-Key eines Service
        Accounts wird nur einmal vollständig angezeigt, direkt nach Erstellung oder Rotation —
        VocaDox speichert oder zeigt ihn danach nie wieder.
      </p>

      {revealedKey && (
        <div
          style={{
            border: "1px solid var(--color-warning)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "color-mix(in srgb, var(--color-warning) 10%, var(--surface-raised))",
          }}
        >
          <strong>API-Key für "{revealedKey.name}" — jetzt kopieren, er wird nicht erneut angezeigt:</strong>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
            <code
              style={{
                flex: 1,
                padding: "var(--space-2)",
                background: "var(--surface-sunken)",
                borderRadius: "var(--radius-sm)",
                overflowWrap: "anywhere",
              }}
            >
              {revealedKey.api_key}
            </code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(revealedKey.api_key)}>
              Kopieren
            </Button>
            <Button variant="secondary" onClick={() => setRevealedKey(null)}>
              Schließen
            </Button>
          </div>
        </div>
      )}

      <DataTable
        columns={columns}
        rows={accountsQuery.data ?? []}
        keyExtractor={(a) => a.id}
        loading={accountsQuery.isLoading}
        rowActions={(a) =>
          canWrite && a.is_active ? (
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <Button variant="secondary" onClick={() => void handleRotate(a.id)}>
                Rotieren
              </Button>
              <Button variant="destructive" onClick={() => void handleRevoke(a.id)}>
                Widerrufen
              </Button>
            </div>
          ) : null
        }
      />

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Neuer Service Account">
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Name" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="Beschreibung (optional)">
            <TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </FormField>
          <FormField label="Organisation" required>
            <Select value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
              <option value="">Organisation wählen…</option>
              {orgsQuery.data?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Owner" hint="Der menschliche Benutzer, dem Schreibaktionen dieses Accounts zugeordnet werden. Erforderlich für jeden Schreib-Scope.">
            <Select value={form.owner_user_id} onChange={(e) => setForm({ ...form, owner_user_id: e.target.value })}>
              <option value="">Kein Owner (nur Lese-Scopes)</option>
              {usersQuery.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.username})
                </option>
              ))}
            </Select>
          </FormField>
          <Card title="Scopes" padded>
            {scopesQuery.data?.scopes.map((scope) => (
              <label key={scope} style={{ display: "block" }}>
                <Checkbox checked={form.scopes.includes(scope)} onChange={() => toggleScope(scope)} /> {scope}
              </label>
            ))}
          </Card>
          <Button variant="primary" onClick={() => void handleCreate()}>
            Erstellen
          </Button>
        </div>
      </Modal>
    </AdminLayout>
  );
}
