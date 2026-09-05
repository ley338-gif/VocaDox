import { MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import styles from "./PageHeader.module.css";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export interface OverflowAction {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  danger?: boolean;
}

interface PageHeaderProps {
  breadcrumb?: BreadcrumbItem[];
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  overflowActions?: OverflowAction[];
}

/**
 * Reusable detail-page header: breadcrumb, title, a meta row (status
 * badges, dates, counts — whatever the caller passes), primary actions on
 * the right, and an optional overflow ("...") menu for secondary/
 * destructive actions that shouldn't compete visually with the primary
 * ones (brief: "destruktive Aktionen ... nicht prominent im Header").
 */
export function PageHeader({ breadcrumb, title, meta, actions, overflowActions }: PageHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [menuOpen]);

  return (
    <div className={styles.wrapper}>
      {breadcrumb && breadcrumb.length > 0 && (
        <nav className={styles.breadcrumb} aria-label="Breadcrumb">
          {breadcrumb.map((item, index) => (
            <span key={index} style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
              {index > 0 && <span aria-hidden="true">/</span>}
              {item.to ? <Link to={item.to}>{item.label}</Link> : <span>{item.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className={styles.topRow}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          {meta && <div className={styles.meta}>{meta}</div>}
        </div>
        {(actions || (overflowActions && overflowActions.length > 0)) && (
          <div className={styles.actions}>
            {actions}
            {overflowActions && overflowActions.length > 0 && (
              <div className={styles.overflowWrap} ref={menuRef}>
                <button
                  type="button"
                  className={styles.overflowButton}
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-label="Weitere Aktionen"
                  aria-expanded={menuOpen}
                >
                  <MoreHorizontal size={18} aria-hidden="true" />
                </button>
                {menuOpen && (
                  <div className={styles.overflowMenu} role="menu">
                    {overflowActions.map((action) => (
                      <button
                        key={action.label}
                        type="button"
                        role="menuitem"
                        className={`${styles.overflowMenuItem} ${action.danger ? styles.overflowMenuItemDanger : ""}`}
                        onClick={() => {
                          setMenuOpen(false);
                          action.onClick();
                        }}
                      >
                        {action.icon}
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
