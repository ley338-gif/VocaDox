import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  addOrganizationMember,
  createOrganization,
  listOrganizationMembers,
  listOrganizations,
  listUsers,
} from "../api/admin";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { Button } from "../design-system/Button";
import { Select, TextInput } from "../design-system/FormControls";

/**
 * Phase 7 Admin Portal Organizations page: list/create organizations and
 * manage membership — closes the pre-existing "organization creation has
 * no HTTP endpoint" gap flagged by the Phase 5/6 validation reports.
 */
export function AdminOrganizationsPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", description: "" });
  const [error, setError] = useState<string | null>(null);
  const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null);

  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers });

  async function handleCreate() {
    if (!csrfToken) return;
    setError(null);
    try {
      await createOrganization(
        { name: form.name, slug: form.slug, description: form.description || null },
        csrfToken
      );
      setForm({ name: "", slug: "", description: "" });
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "organizations"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to create organization");
    }
  }

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>
          Organizations
        </h1>
        <Button variant="primary" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "Cancel" : "New organization"}
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
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextInput
            placeholder="Slug (e.g. general-medicine)"
            value={form.slug}
            onChange={(e) => setForm({ ...form, slug: e.target.value })}
          />
          <TextInput
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          {error && <p style={{ color: "var(--color-danger)" }}>{error}</p>}
          <Button variant="primary" onClick={() => void handleCreate()}>
            Create
          </Button>
        </div>
      )}

      <div style={{ marginTop: "var(--space-6)" }}>
        {orgsQuery.data?.map((org) => (
          <div
            key={org.id}
            style={{
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
              marginTop: "var(--space-3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{org.name}</strong>{" "}
                <code style={{ color: "var(--text-muted)" }}>({org.slug})</code>
              </div>
              <Button
                variant="secondary"
                onClick={() => setExpandedOrgId(expandedOrgId === org.id ? null : org.id)}
              >
                {expandedOrgId === org.id ? "Hide members" : "Show members"}
              </Button>
            </div>
            {org.description && (
              <p style={{ color: "var(--text-secondary)", marginTop: "var(--space-2)" }}>
                {org.description}
              </p>
            )}
            {expandedOrgId === org.id && (
              <OrgMembers orgId={org.id} users={usersQuery.data ?? []} />
            )}
          </div>
        ))}
      </div>
    </AdminLayout>
  );
}

function OrgMembers({
  orgId,
  users,
}: {
  orgId: string;
  users: { id: string; username: string }[];
}) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState("");
  const membersQuery = useQuery({
    queryKey: ["admin", "organization-members", orgId],
    queryFn: () => listOrganizationMembers(orgId),
  });

  async function handleAdd() {
    if (!csrfToken || !selectedUserId) return;
    await addOrganizationMember(orgId, selectedUserId, csrfToken);
    setSelectedUserId("");
    await queryClient.invalidateQueries({ queryKey: ["admin", "organization-members", orgId] });
  }

  const usernameById = new Map(users.map((u) => [u.id, u.username]));

  return (
    <div style={{ marginTop: "var(--space-3)" }}>
      <ul style={{ color: "var(--text-secondary)" }}>
        {membersQuery.data?.map((m) => (
          <li key={m.id}>{usernameById.get(m.user_id) ?? m.user_id}</li>
        ))}
      </ul>
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        <Select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
          <option value="">Add a user…</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </Select>
        <Button variant="secondary" onClick={() => void handleAdd()}>
          Add
        </Button>
      </div>
    </div>
  );
}
