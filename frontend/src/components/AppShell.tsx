import type { ReactNode } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/useAuth";
import styles from "./AppShell.module.css";

/**
 * Minimal navigation chrome. This is NOT the full workspace layout from
 * "VocaDox - Userinterface.png" (sidebar with Übersicht / Konversationen /
 * Aufgaben / ... / System) — that ships alongside the domain features it
 * navigates to, in later phases. Phase 1 adds session-aware nav: a Log in
 * link when signed out, and /app (+ /admin, if permitted) when signed in.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, hasPermission } = useAuth();

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <span className={styles.brand}>VocaDox</span>
        <nav className={styles.nav}>
          <Link to="/">Übersicht</Link>
          <Link to="/design-system">Design System</Link>
          {user ? (
            <>
              <Link to="/app">App</Link>
              <Link to="/app/conversations">Conversations</Link>
              {hasPermission("system:admin") && <Link to="/admin">Admin</Link>}
              {hasPermission("template:read") && (
                <Link to="/admin/templates">Templates</Link>
              )}
            </>
          ) : (
            <Link to="/login">Log in</Link>
          )}
        </nav>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
