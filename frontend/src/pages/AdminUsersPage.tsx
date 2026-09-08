import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import {
  type AdminOrganization,
  type AdminUserDetail,
  createUser,
  defaultAvatarForGender,
  getUser,
  isAutoManagedAvatar,
  listGroups,
  listOrganizations,
  listUsers,
  setUserPassword,
  updateUser,
  uploadAvatar,
} from "../api/admin";
import { ApiError, type Gender } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { AdminLayout } from "../components/AdminLayout";
import { AvatarPicker } from "../components/AvatarPicker";
import { AvatarThumb } from "../components/AvatarThumb";
import { Badge } from "../design-system/Badge";
import { Button } from "../design-system/Button";
import { FormField } from "../design-system/FormField";
import { Checkbox, Select, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState, Skeleton } from "../design-system/States";
import { DataTable, type DataTableColumn } from "../design-system/Table";

const GENDER_LABELS: Record<Gender, string> = {
  male: "männlich",
  female: "weiblich",
  diverse: "divers",
};

interface UserRow {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  avatar_asset_key: string | null;
}

/**
 * Phase 7 Admin Portal Users page: list/view/create/edit/deactivate users,
 * reset passwords, and assign groups/organizations — over the exact
 * Phase 1 RBAC model (app.identity.router's admin endpoints), never a
 * parallel permission system. Deactivation, never hard deletion.
 *
 * Post-GA: editing a user (name/gender/avatar/groups/organizations) and
 * an admin-initiated password reset both open via `editUserId`/
 * `passwordUserId` — from either clicking the row's display name (a
 * text-styled button, not just decoration) or a row action button,
 * matching AdminServiceAccountsPage's multi-button `rowActions` pattern.
 */
export function AdminUsersPage() {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", display_name: "", email: "" });
  const [error, setError] = useState<string | null>(null);
  const [editUserId, setEditUserId] = useState<string | null>(null);
  const [passwordUserId, setPasswordUserId] = useState<string | null>(null);

  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listUsers });
  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listGroups });
  const orgsQuery = useQuery({ queryKey: ["admin", "organizations"], queryFn: listOrganizations });

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
  const orgNameById = new Map((orgsQuery.data ?? []).map((o) => [o.id, o.name]));

  const columns: DataTableColumn<UserRow>[] = [
    {
      key: "avatar",
      header: "",
      render: (row) => <AvatarThumb assetKey={row.avatar_asset_key} label={row.display_name} />,
    },
    { key: "username", header: "Benutzername", render: (row) => row.username, sortable: true, sortValue: (row) => row.username },
    {
      key: "display_name",
      header: "Anzeigename",
      render: (row) => (
        <Button variant="tertiary" type="button" onClick={() => setEditUserId(row.id)}>
          {row.display_name}
        </Button>
      ),
    },
    { key: "email", header: "E-Mail", render: (row) => row.email ?? "—" },
    { key: "groups", header: "Gruppen", render: (row) => <UserGroups userId={row.id} groupNameById={groupNameById} /> },
    { key: "organizations", header: "Organisationen", render: (row) => <UserOrganizations userId={row.id} orgNameById={orgNameById} /> },
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
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant="secondary" onClick={() => setEditUserId(row.id)}>
              Bearbeiten
            </Button>
            <Button variant="secondary" onClick={() => setPasswordUserId(row.id)}>
              Passwort setzen
            </Button>
            <Button variant="secondary" onClick={() => void handleToggleActive(row.id, row.is_active)}>
              {row.is_active ? "Deaktivieren" : "Reaktivieren"}
            </Button>
          </div>
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

      {editUserId && (
        <EditUserModal
          userId={editUserId}
          groups={groupsQuery.data ?? []}
          organizations={orgsQuery.data ?? []}
          onClose={() => setEditUserId(null)}
        />
      )}

      {passwordUserId && (
        <SetPasswordModal userId={passwordUserId} onClose={() => setPasswordUserId(null)} />
      )}
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

function UserOrganizations({
  userId,
  orgNameById,
}: {
  userId: string;
  orgNameById: Map<string, string>;
}) {
  const detailQuery = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => getUser(userId),
  });
  const orgIds = detailQuery.data?.organization_ids ?? [];
  if (orgIds.length === 0) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return <>{orgIds.map((id) => orgNameById.get(id) ?? id).join(", ")}</>;
}

interface EditForm {
  display_name: string;
  first_name: string;
  last_name: string;
  email: string;
  gender: Gender | "";
  avatar_asset_key: string | null;
  group_ids: string[];
  organization_ids: string[];
}

function emptyEditForm(detail: AdminUserDetail): EditForm {
  return {
    display_name: detail.display_name,
    first_name: detail.first_name ?? "",
    last_name: detail.last_name ?? "",
    email: detail.email ?? "",
    gender: detail.gender ?? "",
    avatar_asset_key: detail.avatar_asset_key,
    group_ids: detail.group_ids,
    organization_ids: detail.organization_ids,
  };
}

function EditUserModal({
  userId,
  groups,
  organizations,
  onClose,
}: {
  userId: string;
  groups: { id: string; name: string }[];
  organizations: AdminOrganization[];
  onClose: () => void;
}) {
  const { csrfToken } = useAuth();
  const queryClient = useQueryClient();
  const detailQuery = useQuery({ queryKey: ["admin", "user", userId], queryFn: () => getUser(userId) });
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (detailQuery.data) setForm(emptyEditForm(detailQuery.data));
  }, [detailQuery.data]);

  function handleGenderChange(gender: Gender | "") {
    setForm((current) =>
      current
        ? {
            ...current,
            gender,
            avatar_asset_key: isAutoManagedAvatar(current.avatar_asset_key)
              ? defaultAvatarForGender(gender || null)
              : current.avatar_asset_key,
          }
        : current
    );
  }

  async function handleSave() {
    if (!csrfToken || !form) return;
    if (!form.display_name.trim()) {
      setError("Anzeigename ist erforderlich.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateUser(
        userId,
        {
          display_name: form.display_name.trim(),
          first_name: form.first_name.trim() || null,
          last_name: form.last_name.trim() || null,
          email: form.email.trim() || null,
          gender: form.gender || null,
          avatar_asset_key: form.avatar_asset_key,
          group_ids: form.group_ids,
          organization_ids: form.organization_ids,
        },
        csrfToken
      );
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "user", userId] });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Benutzer konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Benutzer bearbeiten">
      {!form ? (
        <Skeleton height="12rem" />
      ) : (
        <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "480px" }}>
          <AvatarPicker
            assetKey={form.avatar_asset_key}
            displayLabel={form.display_name}
            onChange={(avatar_asset_key) => setForm({ ...form, avatar_asset_key })}
            onUpload={(file) => {
              if (!csrfToken) throw new Error("Fehlendes CSRF-Token.");
              return uploadAvatar(file, csrfToken);
            }}
          />

          <FormField label="Vorname">
            <TextInput value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </FormField>
          <FormField label="Nachname">
            <TextInput value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </FormField>
          <FormField label="Anzeigename" required>
            <TextInput value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </FormField>
          <FormField label="E-Mail">
            <TextInput value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </FormField>
          <FormField label="Geschlecht">
            <Select value={form.gender} onChange={(e) => handleGenderChange(e.target.value as Gender | "")}>
              <option value="">keine Angabe</option>
              <option value="male">{GENDER_LABELS.male}</option>
              <option value="female">{GENDER_LABELS.female}</option>
              <option value="diverse">{GENDER_LABELS.diverse}</option>
            </Select>
          </FormField>

          <div>
            <p style={{ marginBottom: "var(--space-1)", fontWeight: 600 }}>Gruppen</p>
            {groups.length === 0 && <p style={{ color: "var(--text-muted)" }}>Keine Gruppen vorhanden.</p>}
            {groups.map((group) => (
              <label key={group.id} style={{ display: "block", marginTop: "var(--space-1)" }}>
                <Checkbox
                  checked={form.group_ids.includes(group.id)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      group_ids: e.target.checked
                        ? [...form.group_ids, group.id]
                        : form.group_ids.filter((id) => id !== group.id),
                    })
                  }
                />{" "}
                {group.name}
              </label>
            ))}
          </div>

          <div>
            <p style={{ marginBottom: "var(--space-1)", fontWeight: 600 }}>Organisationen</p>
            {organizations.length === 0 && <p style={{ color: "var(--text-muted)" }}>Keine Organisationen vorhanden.</p>}
            {organizations.map((org) => (
              <label key={org.id} style={{ display: "block", marginTop: "var(--space-1)" }}>
                <Checkbox
                  checked={form.organization_ids.includes(org.id)}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      organization_ids: e.target.checked
                        ? [...form.organization_ids, org.id]
                        : form.organization_ids.filter((id) => id !== org.id),
                    })
                  }
                />{" "}
                {org.name}
              </label>
            ))}
          </div>

          {error && <ErrorState message={error} />}
          <Button variant="primary" disabled={saving} onClick={() => void handleSave()}>
            Speichern
          </Button>
        </div>
      )}
    </Modal>
  );
}

function SetPasswordModal({ userId, onClose }: { userId: string; onClose: () => void }) {
  const { csrfToken } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = password.length > 0 && password.length < 12;
  const mismatch = confirm.length > 0 && password !== confirm;
  const canSubmit = password.length >= 12 && password === confirm;

  async function handleSubmit() {
    if (!csrfToken || !canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await setUserPassword(userId, password, csrfToken);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Passwort konnte nicht gesetzt werden.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Passwort setzen">
      <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "400px" }}>
        <p style={{ color: "var(--text-secondary)" }}>
          Setzt das Passwort dieses Benutzers direkt neu — ohne Bestätigung per E-Mail.
        </p>
        <FormField label="Neues Passwort" required>
          <TextInput type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
        {tooShort && (
          <p style={{ color: "var(--color-danger)", fontSize: "var(--font-caption-size)" }}>
            Mindestens 12 Zeichen.
          </p>
        )}
        <FormField label="Passwort wiederholen" required>
          <TextInput type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </FormField>
        {mismatch && (
          <p style={{ color: "var(--color-danger)", fontSize: "var(--font-caption-size)" }}>
            Die Passwörter stimmen nicht überein.
          </p>
        )}
        {error && <ErrorState message={error} />}
        <Button variant="primary" disabled={!canSubmit || saving} onClick={() => void handleSubmit()}>
          Passwort setzen
        </Button>
      </div>
    </Modal>
  );
}
