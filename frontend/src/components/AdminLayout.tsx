import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";

import { useAuth } from "../auth/useAuth";

/**
 * Phase 7 Admin Portal shell (spec §48): a persistent sidebar organized
 * into the exact section groups the spec's mockup shows — Dashboard /
 * MANAGEMENT / AI / OPERATIONS / SECURITY / SYSTEM. Each link is hidden
 * (not just disabled) unless the current user actually has the
 * permission that section's page enforces server-side — the sidebar is a
 * convenience, never the security boundary (every page itself is wrapped
 * in `RequirePermission` in App.tsx).
 *
 * Deliberately excludes items the roadmap places in later phases
 * (Dictionaries, Evaluation, Service Accounts/API/Webhooks, Backups) —
 * see docs/architecture/future-considerations.md's Phase 7 additions.
 */

interface NavItem {
  to: string;
  label: string;
  permission: string;
}

interface NavSection {
  title: string | null;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  { title: null, items: [{ to: "/admin", label: "Dashboard", permission: "system:admin" }] },
  {
    title: "Management",
    items: [
      { to: "/admin/users", label: "Users", permission: "user:manage" },
      { to: "/admin/groups", label: "Groups", permission: "group:manage" },
      { to: "/admin/organizations", label: "Organizations", permission: "organization:manage" },
      { to: "/admin/templates", label: "Templates", permission: "template:read" },
    ],
  },
  {
    title: "AI",
    items: [
      { to: "/admin/models", label: "Models", permission: "provider:read" },
      { to: "/admin/speech", label: "Speech", permission: "provider:read" },
      { to: "/admin/diarization", label: "Diarization", permission: "provider:read" },
      { to: "/admin/profiles", label: "Processing Profiles", permission: "processing-profile:read" },
      { to: "/admin/prompts", label: "Prompts", permission: "template:read" },
    ],
  },
  {
    title: "Operations",
    items: [
      { to: "/admin/jobs", label: "Jobs", permission: "system:admin" },
      { to: "/admin/workers", label: "Workers", permission: "system:admin" },
      { to: "/admin/storage", label: "Storage", permission: "system:admin" },
      { to: "/admin/retention", label: "Retention", permission: "retention:read" },
    ],
  },
  {
    title: "Security",
    items: [
      { to: "/admin/authentication", label: "Authentication", permission: "system:admin" },
      { to: "/admin/audit", label: "Audit", permission: "audit:read" },
    ],
  },
  {
    title: "System",
    items: [{ to: "/admin/about", label: "About & Licenses", permission: "system:admin" }],
  },
];

export function AdminLayout({ children }: { children: ReactNode }) {
  const { hasPermission } = useAuth();
  const location = useLocation();

  return (
    <div style={{ display: "flex", gap: "var(--space-8)", alignItems: "flex-start" }}>
      <nav
        aria-label="Admin"
        style={{
          width: "220px",
          flexShrink: 0,
          borderRight: "1px solid var(--border-default)",
          paddingRight: "var(--space-4)",
        }}
      >
        {SECTIONS.map((section, idx) => {
          const visibleItems = section.items.filter((item) => hasPermission(item.permission));
          if (visibleItems.length === 0) return null;
          return (
            <div key={section.title ?? `section-${idx}`} style={{ marginBottom: "var(--space-6)" }}>
              {section.title && (
                <div
                  style={{
                    fontSize: "var(--font-caption-size)",
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "var(--space-2)",
                  }}
                >
                  {section.title}
                </div>
              )}
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {visibleItems.map((item) => {
                  const active = location.pathname === item.to;
                  return (
                    <li key={item.to}>
                      <Link
                        to={item.to}
                        style={{
                          display: "block",
                          padding: "var(--space-2) var(--space-3)",
                          borderRadius: "var(--radius-sm)",
                          color: active ? "var(--accent)" : "var(--text-secondary)",
                          background: active ? "var(--accent-subtle)" : "transparent",
                          fontWeight: active ? 600 : 400,
                          textDecoration: "none",
                        }}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  );
}
