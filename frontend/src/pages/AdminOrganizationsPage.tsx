import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
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
import { Card } from "../design-system/Card";
import { FormField } from "../design-system/FormField";
import { Select, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";

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
      setError(err instanceof Error ? err.message : "Organisation konnte nicht erstellt werden.");
    }
  }

  return (
    <AdminLayout>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-4)" }}>
        <h1 style={{ fontSize: "var(--font-h1-size)", lineHeight: "var(--font-h1-line)" }}>Organisationen</h1>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          <Plus size={16} aria-hidden="true" /> Neue Organisation
        </Button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {orgsQuery.data?.map((org) => (
          <Card key={org.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong>{org.name}</strong>{" "}
                <code style={{ color: "var(--text-muted)" }}>({org.slug})</code>
              </div>
              <Button
                variant="secondary"
                onClick={() => setExpandedOrgId(expandedOrgId === org.id ? null : org.id)}
              >
                {expandedOrgId === org.id ? "Mitglieder ausblenden" : "Mitglieder anzeigen"}
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
          </Card>
        ))}
      </div>

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Neue Organisation">
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormField label="Name" required>
            <TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label="Slug" hint="z. B. general-medicine" required>
            <TextInput value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
          </FormField>
          <FormField label="Beschreibung (optional)">
            <TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
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
          <option value="">Benutzer hinzufügen…</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </Select>
        <Button variant="secondary" onClick={() => void handleAdd()}>
          Hinzufügen
        </Button>
      </div>
    </div>
  );
}
