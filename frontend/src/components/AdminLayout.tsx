import type { ReactNode } from "react";

/**
 * Thin content wrapper for admin pages. The actual admin navigation
 * sidebar now lives in the unified AppShell (see ./navigation.ts,
 * ADMIN_SECTIONS) — this used to render its own separate sidebar nested
 * inside AppShell's topbar, producing double chrome. Kept as a component
 * (rather than removed) so all 22 Admin*Page.tsx files that already wrap
 * themselves in <AdminLayout> don't need touching in this stage; a later
 * redesign stage may fold this away entirely once those pages are
 * revisited individually.
 */
export function AdminLayout({ children }: { children: ReactNode }) {
  return <div style={{ maxWidth: "1200px" }}>{children}</div>;
}
