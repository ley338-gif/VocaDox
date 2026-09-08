import { useState } from "react";

import { defaultAvatarForGender, isAutoManagedAvatar } from "../api/admin";
import { ApiError, type Gender, updateMe, uploadMyAvatar } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../design-system/Button";
import { FormField } from "../design-system/FormField";
import { Select, TextInput } from "../design-system/FormControls";
import { Modal } from "../design-system/Modal";
import { ErrorState } from "../design-system/States";
import { AvatarPicker } from "./AvatarPicker";

const GENDER_LABELS: Record<Gender, string> = {
  male: "männlich",
  female: "weiblich",
  diverse: "divers",
};

/**
 * Self-service counterpart to AdminUsersPage's EditUserModal, opened from
 * AppShell's user menu ("Mein Profil") — every authenticated user gets
 * this, "entsprechend seiner Rechte": personal identity fields only (no
 * group/organization/is_active control, which stays admin-only via
 * `PATCH /admin/users/{id}` — see `SelfUpdateRequest`'s docstring on the
 * backend for why that split is enforced server-side, not just hidden
 * here). Uses `PATCH /auth/me`/`POST /auth/me/avatar`, not the admin
 * `/admin/users/*` surface, so it works with no permission beyond being
 * logged in.
 */
export function MyProfileModal({ onClose }: { onClose: () => void }) {
  const { user, csrfToken, refreshUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.displayName ?? "");
  const [firstName, setFirstName] = useState(user?.firstName ?? "");
  const [lastName, setLastName] = useState(user?.lastName ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [gender, setGender] = useState<Gender | "">(user?.gender ?? "");
  const [avatarAssetKey, setAvatarAssetKey] = useState<string | null>(user?.avatarAssetKey ?? null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleGenderChange(next: Gender | "") {
    setGender(next);
    if (isAutoManagedAvatar(avatarAssetKey)) {
      setAvatarAssetKey(defaultAvatarForGender(next || null));
    }
  }

  async function handleSave() {
    if (!csrfToken) return;
    if (!displayName.trim()) {
      setError("Anzeigename ist erforderlich.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateMe(
        {
          display_name: displayName.trim(),
          first_name: firstName.trim() || null,
          last_name: lastName.trim() || null,
          email: email.trim() || null,
          gender: gender || null,
          avatar_asset_key: avatarAssetKey,
        },
        csrfToken
      );
      await refreshUser();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Profil konnte nicht gespeichert werden.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Mein Profil">
      <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "420px" }}>
        <AvatarPicker
          assetKey={avatarAssetKey}
          displayLabel={displayName}
          onChange={setAvatarAssetKey}
          onUpload={(file) => {
            if (!csrfToken) throw new Error("Fehlendes CSRF-Token.");
            return uploadMyAvatar(file, csrfToken);
          }}
        />

        <FormField label="Vorname">
          <TextInput value={firstName} onChange={(e) => setFirstName(e.target.value)} />
        </FormField>
        <FormField label="Nachname">
          <TextInput value={lastName} onChange={(e) => setLastName(e.target.value)} />
        </FormField>
        <FormField label="Anzeigename" required>
          <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </FormField>
        <FormField label="E-Mail">
          <TextInput value={email} onChange={(e) => setEmail(e.target.value)} />
        </FormField>
        <FormField label="Geschlecht">
          <Select value={gender} onChange={(e) => handleGenderChange(e.target.value as Gender | "")}>
            <option value="">keine Angabe</option>
            <option value="male">{GENDER_LABELS.male}</option>
            <option value="female">{GENDER_LABELS.female}</option>
            <option value="diverse">{GENDER_LABELS.diverse}</option>
          </Select>
        </FormField>

        {error && <ErrorState message={error} />}
        <Button variant="primary" disabled={saving} onClick={() => void handleSave()}>
          Speichern
        </Button>
      </div>
    </Modal>
  );
}
