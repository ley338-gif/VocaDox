import type { ReactNode } from "react";

import styles from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  disabled?: boolean;
}

interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  idPrefix?: string;
}

export function Tabs({ items, activeId, onChange, idPrefix = "tab" }: TabsProps) {
  return (
    <div className={styles.tablist} role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          id={`${idPrefix}-${item.id}`}
          aria-selected={item.id === activeId}
          aria-controls={`${idPrefix}-panel-${item.id}`}
          disabled={item.disabled}
          className={`${styles.tab} ${item.id === activeId ? styles.tabActive : ""}`}
          onClick={() => onChange(item.id)}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({
  id,
  activeId,
  idPrefix = "tab",
  children,
}: {
  id: string;
  activeId: string;
  idPrefix?: string;
  children: ReactNode;
}) {
  if (id !== activeId) return null;
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-${id}`}
      className={styles.panel}
    >
      {children}
    </div>
  );
}
