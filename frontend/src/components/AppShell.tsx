import type { ReactNode } from "react";
import { Link } from "react-router";

import styles from "./AppShell.module.css";

/**
 * Minimal navigation chrome for Phase 0. This is NOT the full workspace
 * layout from "VocaDox - Userinterface.png" (sidebar with Übersicht /
 * Konversationen / Aufgaben / ... / System) — that ships alongside the
 * domain features it navigates to, starting Phase 1+. For now it only
 * hosts the /design-system living style guide.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <span className={styles.brand}>VocaDox</span>
        <nav className={styles.nav}>
          <Link to="/">Übersicht</Link>
          <Link to="/design-system">Design System</Link>
        </nav>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
