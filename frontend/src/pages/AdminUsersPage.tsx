import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";

import { createUser, getUser, listGroups, listUsers, updateUser } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { FormField } from "../design-system/FormField";
import { TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

interface UserRow {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
}

/**
 * Phase 7 Admin Portal Users page: list/view/create/deactivate users and
 * assign groups — over the exact Phase 1 RBAC model
 * (app.identity.router's admin endpoints), never a parallel permission
 * system. Deactivation, never hard deletion.
 */
export function AdminUsersPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", display_name: "", email: "" });
  const [error, setError] = useState<string | null>(null);

  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers });
  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listGroups });

  async function handleCreate() {
    if (!csrfToken) return;
    setError(null);
    try {
      await createUser(
        {
          username: form.username,
          password: form.password,
          display_name: form.display_name,
          email: form.email || null,
        },
        csrfToken
      );
      setForm({ username: "", password: "", display_name: "", email: "" });
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Benutzer konnte nicht erstellt werden.");
    }
  }

  async function handleToggleActive(userId: string, isActive: boolean) {
    if (!csrfToken) return;
    await updateUser(userId, { is_active: !isActive }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  }

  const groupNameById = new Map((groupsQuery.data ?? []).map((g) => [g.id, g.name]));

  const columns: DataTableColumn<UserRow>[] = [
    { key: "username", header: "Benutzername", render: (row) => row.username, sortable: true, sortValue: (row) => row.username },
    { key: "display_name", header: "Anzeigename", render: (row) => row.display_name },
    { key: "email", header: "E-Mail", render: (row) => row.email ?? "—" },
    { key: "groups", header: "Gruppen", render: (row) => <UserGroups userId={row.id} groupNameById={groupNameById} /> },
    {
      key: "status",
      header: "Status",
      render: (row) => <Badge tone={row.is_active ? "success" : "neutral"}>{row.is_active ? "Aktiv" : "Deaktiviert"}</Badge>,
    },
  ];

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Benutzer</h1>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          <Plus size={16} aria-hidden="true" /> Neuer Benutzer
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={usersQuery.data ?? []}
        keyExtractor={(row) => row.id}
        loading={usersQuery.isLoading}
        rowActions={(row) => (
          <Button variant="secondary" onClick={() => void handleToggleActive(row.id, row.is_active)}>
            {row.is_active ? "Deaktivieren" : "Reaktivieren"}
          </Button>
        )}
        empty={<p style={{ color: "var(--text-muted)" }}>Keine Benutzer.</p>}
      />

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Neuer Benutzer">
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Benutzername" required>
            <TextInput value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </FormField>
          <FormField label="Anzeigename" required>
            <TextInput value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </FormField>
          <FormField label="E-Mail (optional)">
            <TextInput value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </FormField>
          <FormField label="Passwort" required>
            <TextInput type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </FormField>
          {error && <ErrorState message={error} />}
          <Button variant="primary" onClick={() => void handleCreate()}>
            Erstellen
          </Button>
        </div>
      </Modal>
    </AdminLayout>
  );
}

function UserGroups({
  userId,
  groupNameById,
}: {
  userId: string;
  groupNameById: Map<string, string>;
}) {
  const detailQuery = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => getUser(userId),
  });
  const groupIds = detailQuery.data?.group_ids ?? [];
  if (groupIds.length === 0) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return <>{groupIds.map((id) => groupNameById.get(id) ?? id).join(", ")}</>;
}
