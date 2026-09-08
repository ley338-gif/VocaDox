import { useId, useState } from "react";

import { AVATAR_PRESETS, avatarUrl } from "../api/admin";
import { ApiError } from "../api/client";
import { Button } from "../design-system/Button";
import { AvatarThumb } from "./AvatarThumb";

/** The editable avatar widget shared by AdminUsersPage's edit modal and
 * MyProfileModal: a large preview, the two bundled presets, a custom-
 * upload button, and a "remove" action once something is set. `onUpload`
 * does the actual network call (admin vs. self-service use different
 * endpoints) and returns the new asset key; this component only manages
 * which key is currently selected. */
export function AvatarPicker({
  assetKey,
  displayLabel,
  onChange,
  onUpload,
}: {
  assetKey: string | null;
  displayLabel: string;
  onChange: (assetKey: string | null) => void;
  onUpload: (file: File) => Promise<{ asset_key: string }>;
}) {
  const inputId = useId();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const { asset_key } = await onUpload(file);
      onChange(asset_key);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Avatar konnte nicht hochgeladen werden.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <p style={{ marginBottom: "var(--space-2)", fontWeight: 600 }}>Avatar</p>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <AvatarThumb assetKey={assetKey} label={displayLabel} size={64} />
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", alignItems: "center" }}>
          {AVATAR_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              aria-label={preset.label}
              onClick={() => onChange(preset.key)}
              style={{
                padding: 0,
                border: assetKey === preset.key ? "2px solid var(--accent)" : "2px solid transparent",
                borderRadius: "50%",
                cursor: "pointer",
                background: "none",
              }}
            >
              <img
                src={avatarUrl(preset.key) ?? undefined}
                alt={preset.label}
                style={{ width: "40px", height: "40px", borderRadius: "50%", objectFit: "cover", display: "block" }}
              />
            </button>
          ))}
          <input
            type="file"
            accept="image/png,image/jpeg"
            disabled={uploading}
            onChange={(e) => void handleFile(e.target.files)}
            style={{ display: "none" }}
            id={inputId}
          />
          <Button
            variant="tertiary"
            type="button"
            disabled={uploading}
            onClick={() => document.getElementById(inputId)?.click()}
          >
            {uploading ? "Lädt hoch…" : "Eigenes Bild…"}
          </Button>
          {assetKey && (
            <Button variant="tertiary" type="button" onClick={() => onChange(null)}>
              Entfernen
            </Button>
          )}
        </div>
      </div>
      {error && (
        <p style={{ color: "var(--color-danger)", fontSize: "var(--font-caption-size)", marginTop: "var(--space-1)" }}>
          {error}
        </p>
      )}
    </div>
  );
}
