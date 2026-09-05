import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ClipboardList,
  Cpu,
  FileText,
  Info,
  LayoutDashboard,
  MessagesSquare,
  Plug,
  ShieldCheck,
  Users,
} from "lucide-react";

/**
 * Single source of truth for the app's sidebar navigation, shared by
 * AppShell for both the /app and /admin sections. Every item's
 * `permission` must match the exact backend permission its target route
 * enforces via RequirePermission in App.tsx — the sidebar link visibility
 * is a convenience, never the security boundary.
 */
export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  permission?: string;
}

export interface NavSection {
  title: string | null;
  items: NavItem[];
}

export const APP_SECTIONS: NavSection[] = [
  {
    title: null,
    items: [
      { to: "/app", label: "Dashboard", icon: LayoutDashboard },
      { to: "/app/conversations", label: "Gespräche", icon: MessagesSquare },
      { to: "/app/tasks", label: "Aufgaben", icon: ClipboardList, permission: "task:read" },
    ],
  },
  {
    title: null,
    items: [{ to: "/admin", label: "Administration", icon: ShieldCheck, permission: "system:admin" }],
  },
];

export const ADMIN_SECTIONS: NavSection[] = [
  { title: null, items: [{ to: "/admin", label: "Dashboard", icon: LayoutDashboard, permission: "system:admin" }] },
  {
    title: "Management",
    items: [
      { to: "/admin/users", label: "Benutzer", icon: Users, permission: "user:manage" },
      { to: "/admin/groups", label: "Gruppen", icon: Users, permission: "group:manage" },
      { to: "/admin/organizations", label: "Organisationen", icon: Users, permission: "organization:manage" },
      { to: "/admin/templates", label: "Vorlagen", icon: FileText, permission: "template:read" },
    ],
  },
  {
    title: "AI",
    items: [
      { to: "/admin/models", label: "Modelle", icon: Cpu, permission: "provider:read" },
      { to: "/admin/speech", label: "Sprache", icon: Cpu, permission: "provider:read" },
      { to: "/admin/diarization", label: "Diarisierung", icon: Cpu, permission: "provider:read" },
      { to: "/admin/profiles", label: "Verarbeitungsprofile", icon: Cpu, permission: "processing-profile:read" },
      { to: "/admin/prompts", label: "Prompts", icon: Cpu, permission: "template:read" },
    ],
  },
  {
    title: "Operations",
    items: [
      { to: "/admin/jobs", label: "Jobs", icon: Activity, permission: "system:admin" },
      { to: "/admin/workers", label: "Worker", icon: Activity, permission: "system:admin" },
      { to: "/admin/storage", label: "Speicher", icon: Activity, permission: "system:admin" },
      { to: "/admin/retention", label: "Aufbewahrung", icon: Activity, permission: "retention:read" },
      { to: "/admin/operations", label: "Betrieb", icon: Activity, permission: "operations:read" },
      { to: "/admin/analytics", label: "Analytics", icon: Activity, permission: "analytics:read" },
      { to: "/admin/evaluation", label: "Evaluation Lab", icon: Activity, permission: "analytics:read" },
    ],
  },
  {
    title: "Integrations",
    items: [
      { to: "/admin/service-accounts", label: "Service Accounts", icon: Plug, permission: "service-account:read" },
      { to: "/admin/webhooks", label: "Webhooks", icon: Plug, permission: "webhook:read" },
    ],
  },
  {
    title: "Security",
    items: [
      { to: "/admin/authentication", label: "Authentifizierung", icon: ShieldCheck, permission: "system:admin" },
      { to: "/admin/audit", label: "Audit", icon: ShieldCheck, permission: "audit:read" },
    ],
  },
  {
    title: "System",
    items: [{ to: "/admin/about", label: "Über & Lizenzen", icon: Info, permission: "system:admin" }],
  },
];
