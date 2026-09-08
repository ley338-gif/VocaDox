import { avatarUrl } from "../api/admin";

/** Renders a user's avatar image at `size` px, or an initials fallback
 * circle when no avatar is set (or the image fails to load) -- shared by
 * AdminUsersPage's table/edit-modal, AppShell's topbar, and
 * MyProfileModal so all three read `avatar_asset_key` the same way. */
export function AvatarThumb({
  assetKey,
  label,
  size = 32,
}: {
  assetKey: string | null | undefined;
  label: string;
  size?: number;
}) {
  const url = avatarUrl(assetKey ?? null);
  if (url) {
    return (
      <img
        src={url}
        alt=""
        style={{ width: size, height: size, borderRadius: "50%", objectFit: "cover", display: "block" }}
      />
    );
  }
  const initial = label.trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--surface-sunken)",
        color: "var(--text-muted)",
        fontSize: size >= 48 ? "var(--font-h2-size)" : "var(--font-caption-size)",
        fontWeight: 600,
        flexShrink: 0,
      }}
    >
      {initial}
    </span>
  );
}
