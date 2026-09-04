import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createUser, getUser, listGroups, listUsers, updateUser } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { TextInput } from "../design-system/FormControls";

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
      setError(err instanceof Error ? err.message : "failed to create user");
    }
  }

  async function handleToggleActive(userId: string, isActive: boolean) {
    if (!csrfToken) return;
    await updateUser(userId, { is_active: !isActive }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  }

  const groupNameById = new Map((groupsQuery.data ?? []).map((g) => [g.id, g.name]));

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Users</h1>
        <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "Cancel" : "New user"}
        </Button>
      </div>

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
            placeholder="Username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <TextInput
            placeholder="Display name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
          <TextInput
            placeholder="Email (optional)"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <TextInput
            placeholder="Password"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
          <Button variant="primary" onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <table style={{ width: "100%", marginTop: "var(--space-6)", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
            <th>Username</th>
            <th>Display name</th>
            <th>Email</th>
            <th>Groups</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {usersQuery.data?.map((user) => (
            <tr key={user.id} style={{ borderBottom: "1px solid var(--border-default)" }}>
              <td>{user.username}</td>
              <td>{user.display_name}</td>
              <td>{user.email ?? "—"}</td>
              <td>
                <UserGroups userId={user.id} groupNameById={groupNameById} />
              </td>
              <td>
                <Badge tone={user.is_active ? "success" : "neutral"}>
                  {user.is_active ? "active" : "deactivated"}
                </Badge>
              </td>
              <td>
                <Button
                  variant="secondary"
                  onClick={() => void handleToggleActive(user.id, user.is_active)}
                >
                  {user.is_active ? "Deactivate" : "Reactivate"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
