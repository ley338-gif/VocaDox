import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, LogOut, Search, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { getDashboard } from "../api/admin";
import { useAuth } from "../auth/useAuth";
import styles from "./AppShell.module.css";
import { ADMIN_SECTIONS, APP_SECTIONS, type NavSection } from "./navigation";

const SIDEBAR_COLLAPSED_KEY = "vocadox.sidebarCollapsed";

function readCollapsedPreference(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Single AppShell for both /app and /admin — replaces the old thin topbar
 * (which had no sidebar at all) and the separate inline-styled AdminLayout
 * sidebar (which was nested inside it, causing double chrome). Section
 * (app vs admin) is derived from the current path; every nav item's
 * visibility is a convenience only — the real security boundary is each
 * route's own RequirePermission in App.tsx.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, hasPermission, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(readCollapsedPreference);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const userMenuRef = useRef<HTMLDivElement>(null);

  const isWorkspaceRoute = Boolean(user) && (location.pathname.startsWith("/app") || location.pathname.startsWith("/admin"));
  const isAdminSection = location.pathname.startsWith("/admin");
  const sections: NavSection[] = isAdminSection ? ADMIN_SECTIONS : APP_SECTIONS;

  const dashboardQuery = useQuery({
    queryKey: ["appshell-health"],
    queryFn: getDashboard,
    enabled: hasPermission("system:admin"),
    refetchInterval: 30000,
  });
  const allHealthy = dashboardQuery.data?.components.every((component) => component.healthy) ?? null;

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // best-effort only
    }
  }, [collapsed]);

  useEffect(() => {
    if (!userMenuOpen) return;
    function onClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [userMenuOpen]);

  const pageTitle = sections
    .flatMap((section) => section.items)
    .find((item) => item.to === location.pathname)?.label;

  if (!isWorkspaceRoute) {
    return (
      <div className={styles.shell}>
        <div className={styles.content}>
          <header className={styles.topbar}>
            <Link to="/" className={styles.brand}>
              VocaDox
            </Link>
            <div className={styles.topbarSpacer} />
            <Link to="/design-system" className={styles.publicNavLink}>
              Design System
            </Link>
            {!user && (
              <Link to="/login" className={styles.publicNavLink}>
                Log in
              </Link>
            )}
          </header>
          <main className={styles.main}>{children}</main>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ""}`}>
        <div className={styles.sidebarHeader}>
          {!collapsed && (
            <Link to="/app" className={styles.brand}>
              VocaDox
            </Link>
          )}
          <button
            type="button"
            className={styles.collapseButton}
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Sidebar erweitern" : "Sidebar einklappen"}
          >
            {collapsed ? <ChevronRight size={16} aria-hidden="true" /> : <ChevronLeft size={16} aria-hidden="true" />}
          </button>
        </div>
        <nav className={styles.nav} aria-label={isAdminSection ? "Administration" : "Hauptnavigation"}>
          {sections.map((section, sectionIndex) => {
            const visibleItems = section.items.filter((item) => !item.permission || hasPermission(item.permission));
            if (visibleItems.length === 0) return null;
            return (
              <div className={styles.navSection} key={section.title ?? `section-${sectionIndex}`}>
                {section.title && !collapsed && <div className={styles.navSectionTitle}>{section.title}</div>}
                <ul className={styles.navList}>
                  {visibleItems.map((item) => {
                    const active = location.pathname === item.to;
                    const Icon = item.icon;
                    return (
                      <li key={item.to}>
                        <Link
                          to={item.to}
                          className={`${styles.navLink} ${active ? styles.navLinkActive : ""}`}
                          title={collapsed ? item.label : undefined}
                        >
                          <Icon size={18} aria-hidden="true" />
                          {!collapsed && <span>{item.label}</span>}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>
        <div className={styles.sidebarFooter}>
          {!collapsed ? (
            <>
              <span>Lokal / On-Prem</span>
              <span>Keine Cloud</span>
              {hasPermission("system:admin") && (
                <div className={styles.sidebarFooterRow}>
                  <ShieldCheck
                    size={14}
                    aria-hidden="true"
                    style={{ color: allHealthy === false ? "var(--color-danger)" : "var(--color-success)" }}
                  />
                  <span>{allHealthy === false ? "Systemstörung" : "Alle Systeme betriebsbereit"}</span>
                </div>
              )}
            </>
          ) : (
            <ShieldCheck
              size={16}
              aria-hidden="true"
              style={{
                color:
                  hasPermission("system:admin") && allHealthy === false
                    ? "var(--color-danger)"
                    : "var(--color-success)",
              }}
            />
          )}
        </div>
      </aside>

      <div className={styles.content}>
        <header className={styles.topbar}>
          {pageTitle && <span className={styles.pageTitle}>{pageTitle}</span>}
          <form
            className={styles.searchForm}
            onSubmit={(event) => {
              event.preventDefault();
              if (searchValue.trim()) {
                navigate(`/app/conversations?q=${encodeURIComponent(searchValue.trim())}`);
              }
            }}
          >
            <Search size={16} className={styles.searchIcon} aria-hidden="true" />
            <input
              type="search"
              className={styles.searchInput}
              placeholder="Gespräche durchsuchen…"
              aria-label="Gespräche durchsuchen"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
            />
          </form>
          <div className={styles.topbarSpacer} />
          <div className={styles.topbarRight} ref={userMenuRef}>
            <button type="button" className={styles.userButton} onClick={() => setUserMenuOpen((open) => !open)}>
              <span className={styles.avatar}>{(user?.displayName ?? "?").slice(0, 1).toUpperCase()}</span>
              {user?.displayName}
            </button>
            {userMenuOpen && (
              <div className={styles.userMenu}>
                <div className={styles.userMenuName}>{user?.displayName}</div>
                <button
                  type="button"
                  className={styles.navLink}
                  style={{ width: "100%", background: "none", border: "none", cursor: "pointer" }}
                  onClick={() => {
                    setUserMenuOpen(false);
                    void logout();
                  }}
                >
                  <LogOut size={16} aria-hidden="true" />
                  <span>Abmelden</span>
                </button>
              </div>
            )}
          </div>
        </header>
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
