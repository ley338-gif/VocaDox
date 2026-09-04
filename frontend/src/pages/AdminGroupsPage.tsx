import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createGroup, getGroup, listGroups, listRoles, updateGroup } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Button } from "../design-system/Button";
import { Checkbox, TextInput } from "../design-system/FormControls";

/**
 * Phase 7 Admin Portal Groups page: manage groups and their role
 * assignments — the exact Phase 1 RBAC model (Group -> GroupRole ->
 * Role -> Permission), never a parallel system.
 */
export function AdminGroupsPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);

  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listGroups });
  const rolesQuery = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  async function handleCreate() {
    if (!csrfToken || !name.trim()) return;
    await createGroup({ name, role_ids: selectedRoleIds }, csrfToken);
    setName("");
    setSelectedRoleIds([]);
    setShowCreate(false);
    await queryClient.invalidateQueries({ queryKey: ["admin", "groups"] });
  }

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Groups</h1>
        <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "Cancel" : "New group"}
        </Button>
      </div>

      {showCreate && (
        <div
          style={{
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginTop: "var(--space-4)",
            maxWidth: "420px",
          }}
        >
          <TextInput placeholder="Group name" value={name} onChange={(e) => setName(e.target.value)} />
          <p style={{ marginTop: "var(--space-3)", fontWeight: 600 }}>Roles</p>
          {rolesQuery.data?.map((role) => (
            <label key={role.id} style={{ display: "block", marginTop: "var(--space-1)" }}>
              <Checkbox
                checked={selectedRoleIds.includes(role.id)}
                onChange={(e) =>
                  setSelectedRoleIds((prev) =>
                    e.target.checked ? [...prev, role.id] : prev.filter((id) => id !== role.id)
                  )
                }
              />{" "}
              {role.name}
            </label>
          ))}
          <Button variant="primary" style={{ marginTop: "var(--space-3)" }} onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <div style={{ marginTop: "var(--space-6)" }}>
        {groupsQuery.data?.map((group) => (
          <GroupRow
            key={group.id}
            groupId={group.id}
            groupName={group.name}
            roles={rolesQuery.data ?? []}
            editing={editingGroupId === group.id}
            onToggleEdit={() =>
              setEditingGroupId((current) => (current === group.id ? null : group.id))
            }
          />
        ))}
      </div>
    </AdminLayout>
  );
}

function GroupRow({
  groupId,
  groupName,
  roles,
  editing,
  onToggleEdit,
}: {
  groupId: string;
  groupName: string;
  roles: { id: string; name: string }[];
  editing: boolean;
  onToggleEdit: () => void;
}) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: ["admin", "group", groupId],
    queryFn: () => getGroup(groupId),
    enabled: editing,
  });

  async function handleToggleRole(roleId: string, checked: boolean) {
    if (!csrfToken || !detailQuery.data) return;
    const current = detailQuery.data.role_ids;
    const next = checked ? [...current, roleId] : current.filter((id) => id !== roleId);
    await updateGroup(groupId, { role_ids: next }, csrfToken);
    await queryClient.invalidateQueries({ queryKey: ["admin", "group", groupId] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "groups"] });
  }

  return (
    <div
      style={{
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        marginTop: "var(--space-3)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{groupName}</strong>
        <Button variant="secondary" onClick={onToggleEdit}>
          {editing ? "Hide roles" : "Manage roles"}
        </Button>
      </div>
      {editing && detailQuery.data && (
        <div style={{ marginTop: "var(--space-3)" }}>
          {roles.map((role) => (
            <label key={role.id} style={{ display: "block", marginTop: "var(--space-1)" }}>
              <Checkbox
                checked={detailQuery.data.role_ids.includes(role.id)}
                onChange={(e) => void handleToggleRole(role.id, e.target.checked)}
              />{" "}
              {role.name}
            </label>
          ))}
          <p style={{ marginTop: "var(--space-3)", color: "var(--text-secondary)" }}>
            Members: {detailQuery.data.member_ids.length}
          </p>
        </div>
      )}
    </div>
  );
}
